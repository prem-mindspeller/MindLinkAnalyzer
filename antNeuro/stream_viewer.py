#!/usr/bin/env python3
"""
ANT Neuro Real-Time EEG Stream Viewer
======================================
Simple GUI to visualize live EEG data from ANT Neuro amplifier.

IMPORTANT: Must connect to amplifier BEFORE importing Qt to avoid USB conflicts!

Usage:
    python stream_viewer.py

Requirements:
    - Python 3.11
    - ANT Neuro amplifier connected
    - eego_sdk in eego_sdk_toolbox folder

Author: BrainLink Companion Team
Date: February 2026
"""

import sys
import os
import numpy as np
from collections import deque
import time

# Add eego SDK to path and DLL directory FIRST - before anything else
SDK_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'eego_sdk_toolbox'
)
if SDK_PATH not in sys.path:
    sys.path.insert(0, SDK_PATH)
    
# Add parent directory for imports
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

if os.path.exists(SDK_PATH):
    try:
        os.add_dll_directory(SDK_PATH)
        print(f"✓ Added DLL directory: {SDK_PATH}")
    except Exception as e:
        print(f"Warning: Could not add DLL directory: {e}")

# ============================================================================
# CRITICAL: Connect to amplifier BEFORE importing Qt!
# Qt interferes with USB device discovery
# ============================================================================

print("Connecting to ANT Neuro amplifier (before Qt init)...")

# Import eego_sdk and our wrapper
sys.path.insert(0, SDK_PATH)
import eego_sdk
print("✓ eego_sdk imported")

# Import our wrapper
from antNeuro.antneuro_data_acquisition import AntNeuroDevice

try:
    print("Creating device interface...")
    global_device = AntNeuroDevice()
    
    print("Discovering amplifiers...")
    global_amplifiers = global_device.discover_amplifiers()
    
    if not global_amplifiers:
        print("ERROR: No amplifiers found!")
        print("Please:")
        print("  1. Connect the ANT Neuro amplifier via USB")
        print("  2. Ensure drivers are installed")
        print("  3. Power on the device")
        print("  4. Restart this application")
        sys.exit(1)
    
    print("Connecting to amplifier...")
    global_amp_info = global_device.connect()
    print(f"✓ Connected to {global_amp_info.type} (S/N: {global_amp_info.serial})")
    print(f"✓ {global_amp_info.channel_count} channels available")
    
except Exception as e:
    print(f"ERROR: Failed to connect to amplifier: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# NOW we can import Qt
print("Initializing Qt GUI...")
os.environ.setdefault('PYQTGRAPH_QT_LIB', 'PySide6')

from PySide6 import QtWidgets, QtCore
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QComboBox, QSpinBox, QGroupBox
)
from PySide6.QtCore import Qt, QTimer
import pyqtgraph as pg

# Already connected to device before Qt import!
# global_device and global_amp_info are available


class EEGStreamViewer(QMainWindow):
    """Real-time EEG stream viewer with multi-channel display"""
    
    def __init__(self, device, amp_info):
        super().__init__()
        self.device = device  # Use pre-connected device
        self.amp_info = amp_info
        self.is_streaming = False
        self.channels_to_display = 8  # Number of channels to show
        self.buffer_size = 500  # Number of samples to display (1 second at 500Hz)
        self.channel_buffers = []
        self.sample_rate = 500
        
        self.init_ui()
        self.update_device_info()
        
    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("ANT Neuro EEG Stream Viewer")
        self.setGeometry(100, 100, 1400, 900)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Control panel
        control_group = QGroupBox("Controls")
        control_layout = QHBoxLayout()
        
        # Device status
        self.status_label = QLabel("Status: Initializing...")
        self.status_label.setStyleSheet("font-weight: bold; color: orange;")
        control_layout.addWidget(self.status_label)
        
        control_layout.addStretch()
        
        # Sampling rate selector
        control_layout.addWidget(QLabel("Sample Rate:"))
        self.rate_combo = QComboBox()
        self.rate_combo.addItems(["500 Hz", "1000 Hz", "2000 Hz", "4000 Hz"])
        self.rate_combo.currentTextChanged.connect(self.on_rate_changed)
        control_layout.addWidget(self.rate_combo)
        
        # Number of channels to display
        control_layout.addWidget(QLabel("Display Channels:"))
        self.channel_spin = QSpinBox()
        self.channel_spin.setRange(1, 64)
        self.channel_spin.setValue(8)
        self.channel_spin.valueChanged.connect(self.on_channels_changed)
        control_layout.addWidget(self.channel_spin)
        
        # Start/Stop button
        self.start_btn = QPushButton("Start Streaming")
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                padding: 8px 20px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.start_btn.clicked.connect(self.toggle_streaming)
        control_layout.addWidget(self.start_btn)
        
        control_group.setLayout(control_layout)
        main_layout.addWidget(control_group)
        
        # Info panel
        info_layout = QHBoxLayout()
        self.info_label = QLabel("Amplifier: Not connected")
        self.fps_label = QLabel("FPS: 0")
        self.data_label = QLabel("Samples: 0")
        info_layout.addWidget(self.info_label)
        info_layout.addStretch()
        info_layout.addWidget(self.fps_label)
        info_layout.addWidget(self.data_label)
        main_layout.addLayout(info_layout)
        
        # Plot widget
        self.plot_widget = pg.GraphicsLayoutWidget()
        self.plot_widget.setBackground('w')
        main_layout.addWidget(self.plot_widget)
        
        # Create plots for each channel
        self.plots = []
        self.curves = []
        self.create_channel_plots()
        
        # Timer for updating display
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_display)
        
        # FPS counter
        self.last_update_time = time.time()
        self.frame_count = 0
        
    def create_channel_plots(self):
        """Create individual plots for each channel"""
        self.plot_widget.clear()
        self.plots = []
        self.curves = []
        self.channel_buffers = []
        
        colors = [
            (255, 0, 0),      # Red
            (0, 0, 255),      # Blue
            (0, 200, 0),      # Green
            (255, 0, 255),    # Magenta
            (255, 140, 0),    # Orange
            (0, 200, 200),    # Cyan
            (148, 0, 211),    # Purple
            (255, 20, 147),   # Pink
        ]
        
        for i in range(self.channels_to_display):
            # Create plot
            plot = self.plot_widget.addPlot(row=i, col=0)
            plot.setLabel('left', f'Ch {i+1}', units='μV')
            plot.showGrid(x=True, y=True, alpha=0.3)
            plot.setYRange(-100, 100)  # Typical EEG range
            
            if i == self.channels_to_display - 1:
                plot.setLabel('bottom', 'Time', units='samples')
            else:
                plot.hideAxis('bottom')
            
            # Create curve
            color_idx = i % len(colors)
            curve = plot.plot(pen=pg.mkPen(color=colors[color_idx], width=2))
            
            self.plots.append(plot)
            self.curves.append(curve)
            
            # Create data buffer
            self.channel_buffers.append(deque(maxlen=self.buffer_size))
    
    def update_device_info(self):
        """Update UI with connected device information"""
        self.info_label.setText(
            f"Amplifier: {self.amp_info.type} (S/N: {self.amp_info.serial}) | "
            f"Channels: {self.amp_info.channel_count}"
        )
        
        self.status_label.setText("Status: Connected - Ready to stream")
        self.status_label.setStyleSheet("font-weight: bold; color: green;")
        self.start_btn.setEnabled(True)
    
    def on_rate_changed(self, text):
        """Handle sample rate change"""
        if self.is_streaming:
            QtWidgets.QMessageBox.warning(
                self,
                "Cannot Change Rate",
                "Stop streaming before changing sample rate."
            )
            return
        
        rate_str = text.split()[0]
        self.sample_rate = int(rate_str)
    
    def on_channels_changed(self, value):
        """Handle number of channels change"""
        if self.is_streaming:
            QtWidgets.QMessageBox.warning(
                self,
                "Cannot Change Channels",
                "Stop streaming before changing channel count."
            )
            return
        
        self.channels_to_display = value
        self.create_channel_plots()
    
    def toggle_streaming(self):
        """Start or stop data streaming"""
        if not self.device:
            return
        
        if not self.is_streaming:
            self.start_streaming()
        else:
            self.stop_streaming()
    
    def start_streaming(self):
        """Start EEG data streaming"""
        try:
            self.device.start_streaming(sample_rate=self.sample_rate)
            self.is_streaming = True
            
            # Update UI
            self.start_btn.setText("Stop Streaming")
            self.start_btn.setStyleSheet("""
                QPushButton {
                    background-color: #dc3545;
                    color: white;
                    padding: 8px 20px;
                    font-weight: bold;
                    border-radius: 5px;
                }
                QPushButton:hover {
                    background-color: #c82333;
                }
            """)
            self.status_label.setText("Status: Streaming...")
            self.status_label.setStyleSheet("font-weight: bold; color: blue;")
            
            self.rate_combo.setEnabled(False)
            self.channel_spin.setEnabled(False)
            
            # Clear buffers
            for buffer in self.channel_buffers:
                buffer.clear()
            
            # Start update timer (30 FPS)
            self.update_timer.start(33)
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Streaming Error",
                f"Failed to start streaming:\n\n{str(e)}"
            )
    
    def stop_streaming(self):
        """Stop EEG data streaming"""
        try:
            self.update_timer.stop()
            self.device.stop_streaming()
            self.is_streaming = False
            
            # Update UI
            self.start_btn.setText("Start Streaming")
            self.start_btn.setStyleSheet("""
                QPushButton {
                    background-color: #28a745;
                    color: white;
                    padding: 8px 20px;
                    font-weight: bold;
                    border-radius: 5px;
                }
                QPushButton:hover {
                    background-color: #218838;
                }
            """)
            self.status_label.setText("Status: Connected - Ready to stream")
            self.status_label.setStyleSheet("font-weight: bold; color: green;")
            
            self.rate_combo.setEnabled(True)
            self.channel_spin.setEnabled(True)
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Stop Error",
                f"Failed to stop streaming:\n\n{str(e)}"
            )
    
    def update_display(self):
        """Update the display with new data"""
        if not self.is_streaming:
            return
        
        try:
            # Read samples (50ms worth of data)
            num_samples = max(10, int(self.sample_rate * 0.05))
            data = self.device.read_samples(num_samples)
            
            if data is None or data.shape[0] == 0:
                return
            
            # Update buffers with new data
            for sample_idx in range(data.shape[0]):
                for ch_idx in range(min(self.channels_to_display, data.shape[1])):
                    self.channel_buffers[ch_idx].append(data[sample_idx, ch_idx])
            
            # Update plots
            for ch_idx in range(self.channels_to_display):
                if len(self.channel_buffers[ch_idx]) > 0:
                    y_data = np.array(self.channel_buffers[ch_idx])
                    x_data = np.arange(len(y_data))
                    self.curves[ch_idx].setData(x_data, y_data)
            
            # Update data counter
            self.data_label.setText(f"Samples: {data.shape[0]} x {data.shape[1]} ch")
            
            # Calculate FPS
            self.frame_count += 1
            current_time = time.time()
            elapsed = current_time - self.last_update_time
            
            if elapsed >= 1.0:
                fps = self.frame_count / elapsed
                self.fps_label.setText(f"FPS: {fps:.1f}")
                self.frame_count = 0
                self.last_update_time = current_time
            
        except Exception as e:
            print(f"Update error: {e}")
            import traceback
            traceback.print_exc()
    
    def closeEvent(self, event):
        """Handle window close"""
        if self.is_streaming:
            self.stop_streaming()
        
        if self.device:
            self.device.disconnect()
        
        event.accept()


def main():
    """Main application entry point"""
    app = QtWidgets.QApplication(sys.argv)
    
    # Set application style
    app.setStyle('Fusion')
    
    # Create and show viewer with pre-connected device
    viewer = EEGStreamViewer(global_device, global_amp_info)
    viewer.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
