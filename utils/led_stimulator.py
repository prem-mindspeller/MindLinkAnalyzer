"""
led_stimulator.py — PySerial controller for the Arduino LED stimulator.

Controls an Arduino running LEDstimulator_serial.ino via serial commands.
The Arduino handles precise 40 Hz LED timing internally; this module
only sends START / STOP / configuration commands.

Usage in the GUI phase-transition handler:
    from utils.led_stimulator import LEDStimulatorController

    # At app startup or task selection
    led = LEDStimulatorController()
    led.connect()        # auto-detects Arduino COM port

    # When 40Hz task phase starts
    led.start_stimulation()

    # When 40Hz task phase ends (or manual stop)
    led.stop_stimulation()

    # Cleanup
    led.disconnect()
"""

from __future__ import annotations

import time
import threading
import logging

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy-import serial so the rest of the app works even if pyserial isn't
# installed (the module simply won't connect).
# ---------------------------------------------------------------------------
_serial_mod = None

def _import_serial():
    global _serial_mod
    if _serial_mod is None:
        try:
            import serial as _s          # type: ignore
            _serial_mod = _s
        except ImportError:
            log.warning("pyserial is not installed — LED stimulator will be unavailable. "
                        "Install with: pip install pyserial")
    return _serial_mod


def _import_serial_tools():
    try:
        import serial.tools.list_ports as lp  # type: ignore
        return lp
    except ImportError:
        return None


# Common Arduino USB vendor IDs
_ARDUINO_VIDS = {
    0x2341,  # Arduino SA
    0x2A03,  # Arduino.org
    0x1A86,  # CH340
    0x0403,  # FTDI
    0x10C4,  # CP210x (Silicon Labs)
}


class LEDStimulatorController:
    """Thread-safe controller for the Arduino LED stimulator."""

    # Default serial settings (must match Arduino firmware)
    BAUD_RATE = 9600
    TIMEOUT = 2.0            # seconds for reads
    RESPONSE_WAIT = 0.5      # seconds to wait for ACK
    STARTUP_DELAY = 2.0      # seconds to wait after opening port (Arduino reset)

    def __init__(self, port: str | None = None, frequency: float = 40.0,
                 duration: float = 150.0, task: int = 1):
        self._port_name = port
        self._frequency = frequency
        self._duration = duration
        self._task = task
        self._ser = None
        self._lock = threading.Lock()
        self._connected = False
        self._stimulating = False
        self._reader_thread: threading.Thread | None = None
        self._reader_running = False
        self._response_lines: list[str] = []

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def connected(self) -> bool:
        return self._connected and self._ser is not None and self._ser.is_open

    @property
    def stimulating(self) -> bool:
        return self._stimulating

    @property
    def port_name(self) -> str | None:
        return self._port_name

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------
    def connect(self, port: str | None = None) -> bool:
        """Connect to the Arduino. Auto-detects port if *port* is None."""
        serial = _import_serial()
        if serial is None:
            log.error("Cannot connect: pyserial not installed")
            return False

        port = port or self._port_name or self._auto_detect_port()
        if port is None:
            log.error("No Arduino port found. Is it plugged in?")
            return False

        with self._lock:
            try:
                if self._ser and self._ser.is_open:
                    self._ser.close()

                self._ser = serial.Serial(
                    port=port,
                    baudrate=self.BAUD_RATE,
                    timeout=self.TIMEOUT,
                )
                self._port_name = port
                log.info(f"Opened serial port {port} @ {self.BAUD_RATE} baud")

                # Arduino resets on serial open; wait for it to boot
                time.sleep(self.STARTUP_DELAY)

                # Start background reader thread
                self._start_reader()

                # Drain any startup messages
                time.sleep(0.3)
                self._drain_startup()

                # Verify connection with PING
                if self._ping():
                    self._connected = True
                    # Send configuration
                    self._send_config()
                    log.info(f"LED stimulator connected on {port}")
                    return True
                else:
                    log.warning(f"Arduino on {port} did not respond to PING")
                    self._ser.close()
                    self._connected = False
                    return False

            except Exception as exc:
                log.error(f"Failed to connect on {port}: {exc}")
                self._connected = False
                return False

    def disconnect(self):
        """Disconnect and clean up."""
        with self._lock:
            self._stop_reader()
            if self._ser and self._ser.is_open:
                try:
                    # Ensure stimulation is stopped
                    if self._stimulating:
                        self._write("STOP")
                    self._ser.close()
                except Exception:
                    pass
            self._connected = False
            self._stimulating = False
            log.info("LED stimulator disconnected")

    # ------------------------------------------------------------------
    # Stimulation control
    # ------------------------------------------------------------------
    def start_stimulation(self) -> bool:
        """Send START command. Returns True if acknowledged."""
        if not self.connected:
            log.warning("Cannot start: not connected")
            return False

        with self._lock:
            self._response_lines.clear()
            self._write("START")
            # Wait for ACK
            ack = self._wait_for_response("ACK_START", timeout=2.0)
            if ack:
                self._stimulating = True
                log.info("LED stimulation STARTED")
                return True
            else:
                log.warning("No ACK_START received from Arduino")
                return False

    def stop_stimulation(self) -> bool:
        """Send STOP command. Returns True if acknowledged."""
        if not self.connected:
            log.warning("Cannot stop: not connected")
            return False

        with self._lock:
            self._response_lines.clear()
            self._write("STOP")
            # Wait for ACK
            ack = self._wait_for_response("ACK_STOP", timeout=2.0)
            self._stimulating = False
            if ack:
                log.info("LED stimulation STOPPED")
                return True
            else:
                # Even without ACK, mark as stopped
                log.warning("No ACK_STOP received, but assuming stopped")
                return False

    def set_frequency(self, freq: float) -> bool:
        """Set stimulation frequency (Hz)."""
        if not self.connected:
            return False
        self._frequency = freq
        with self._lock:
            self._write(f"FREQ:{freq:.1f}")
            return self._wait_for_response("SET_FREQ", timeout=1.0)

    def set_duration(self, dur: float) -> bool:
        """Set stimulation duration (seconds)."""
        if not self.connected:
            return False
        self._duration = dur
        with self._lock:
            self._write(f"DUR:{dur:.1f}")
            return self._wait_for_response("SET_DUR", timeout=1.0)

    def set_task(self, task: int) -> bool:
        """Set task mode (1-8)."""
        if not self.connected:
            return False
        self._task = task
        with self._lock:
            self._write(f"TASK:{task}")
            return self._wait_for_response("SET_TASK", timeout=1.0)

    def get_status(self) -> str | None:
        """Query Arduino status. Returns status string or None."""
        if not self.connected:
            return None
        with self._lock:
            self._response_lines.clear()
            self._write("STATUS")
            if self._wait_for_response("STATUS:", timeout=1.0):
                for line in self._response_lines:
                    if line.startswith("STATUS:"):
                        return line
            return None

    # ------------------------------------------------------------------
    # Port detection
    # ------------------------------------------------------------------
    def _auto_detect_port(self) -> str | None:
        """Scan COM ports for an Arduino."""
        lp = _import_serial_tools()
        if lp is None:
            return None
        ports = list(lp.comports())
        # Prefer known Arduino VIDs
        for p in ports:
            if p.vid and p.vid in _ARDUINO_VIDS:
                log.info(f"Auto-detected Arduino on {p.device} "
                         f"(VID=0x{p.vid:04X}, {p.description})")
                return p.device
        # Fallback: any port with 'Arduino' or 'CH340' in description
        for p in ports:
            desc = (p.description or '').lower()
            if any(kw in desc for kw in ('arduino', 'ch340', 'ch341', 'cp210', 'ftdi')):
                log.info(f"Auto-detected Arduino-like device on {p.device}: {p.description}")
                return p.device
        if ports:
            log.info(f"No Arduino VID match; available ports: "
                     f"{[p.device for p in ports]}")
        return None

    @staticmethod
    def list_ports() -> list[dict]:
        """Return list of available COM ports with details."""
        lp = _import_serial_tools()
        if lp is None:
            return []
        result = []
        for p in lp.comports():
            result.append({
                'device': p.device,
                'description': p.description or '',
                'vid': f"0x{p.vid:04X}" if p.vid else None,
                'pid': f"0x{p.pid:04X}" if p.pid else None,
                'serial_number': p.serial_number,
            })
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _write(self, cmd: str):
        """Write a command string followed by newline."""
        if self._ser and self._ser.is_open:
            msg = cmd.strip() + '\n'
            self._ser.write(msg.encode('ascii'))
            self._ser.flush()
            log.debug(f"TX: {cmd}")

    def _ping(self) -> bool:
        """Send PING, expect PONG."""
        self._response_lines.clear()
        self._write("PING")
        return self._wait_for_response("PONG", timeout=3.0)

    def _send_config(self):
        """Send current task/freq/duration to Arduino."""
        try:
            self._write(f"TASK:{self._task}")
            time.sleep(0.1)
            self._write(f"FREQ:{self._frequency:.1f}")
            time.sleep(0.1)
            self._write(f"DUR:{self._duration:.1f}")
            time.sleep(0.1)
        except Exception as exc:
            log.warning(f"Config send error: {exc}")

    def _drain_startup(self):
        """Read and log any Arduino boot messages."""
        for line in list(self._response_lines):
            log.debug(f"Arduino boot: {line}")
        self._response_lines.clear()

    def _wait_for_response(self, keyword: str, timeout: float = 2.0) -> bool:
        """Wait up to *timeout* seconds for a response line containing *keyword*."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for line in self._response_lines:
                if keyword in line:
                    return True
            time.sleep(0.05)
        return False

    # ------------------------------------------------------------------
    # Background reader thread
    # ------------------------------------------------------------------
    def _start_reader(self):
        """Start a background thread that reads serial lines."""
        self._reader_running = True
        self._reader_thread = threading.Thread(
            target=self._reader_loop, daemon=True, name="LEDStim-reader"
        )
        self._reader_thread.start()

    def _stop_reader(self):
        """Stop background reader thread."""
        self._reader_running = False
        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=2.0)
        self._reader_thread = None

    def _reader_loop(self):
        """Continuously read lines from serial in the background."""
        while self._reader_running:
            try:
                if self._ser and self._ser.is_open and self._ser.in_waiting:
                    line = self._ser.readline().decode('ascii', errors='replace').strip()
                    if line:
                        log.debug(f"RX: {line}")
                        self._response_lines.append(line)
                        # Keep buffer bounded
                        if len(self._response_lines) > 200:
                            self._response_lines = self._response_lines[-100:]
                        # Track stimulation state from Arduino responses
                        if "STIM_DONE" in line or "STIM_STOPPED" in line:
                            self._stimulating = False
                else:
                    time.sleep(0.02)
            except Exception:
                if self._reader_running:
                    time.sleep(0.1)


# ===========================================================================
# Test/Demo Mode
# ===========================================================================
if __name__ == "__main__":
    import sys
    
    # Enable logging to console
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%H:%M:%S'
    )
    
    print("\n" + "="*70)
    print("LED Stimulator Test Mode")
    print("="*70)
    
    # List available ports
    print("\n1. Scanning for COM ports...")
    ports = LEDStimulatorController.list_ports()
    if not ports:
        print("   No COM ports found!")
        sys.exit(1)
    
    print(f"   Found {len(ports)} port(s):")
    for i, p in enumerate(ports, 1):
        print(f"   {i}. {p['device']} - {p['description']}")
        if p['vid']:
            print(f"      VID={p['vid']}, PID={p['pid']}")
    
    # Create controller
    print("\n2. Creating LED stimulator controller...")
    controller = LEDStimulatorController(frequency=40.0, duration=10.0, task=1)
    print(f"   Configured: 40 Hz, 10 second test duration")
    
    # Auto-connect
    print("\n3. Attempting to connect to Arduino...")
    if controller.connect():
        print(f"   ✓ Connected to {controller.port_name}")
    else:
        print("   ✗ Connection failed!")
        print("\n   Troubleshooting:")
        print("   - Is the Arduino plugged in via USB?")
        print("   - Is the LEDstimulator_serial.ino firmware uploaded?")
        print("   - Try unplugging and replugging the Arduino")
        sys.exit(1)
    
    # Get status
    print("\n4. Querying Arduino status...")
    status = controller.get_status()
    if status:
        print(f"   {status}")
    
    # Interactive test menu
    print("\n" + "="*70)
    print("Interactive Test Menu")
    print("="*70)
    print("  1. Start 10-second stimulation test")
    print("  2. Start stimulation (runs until manually stopped)")
    print("  3. Stop stimulation")
    print("  4. Set frequency")
    print("  5. Set duration")
    print("  6. Get status")
    print("  7. Disconnect and exit")
    print("="*70)
    
    try:
        while True:
            choice = input("\nEnter choice (1-7): ").strip()
            
            if choice == "1":
                print("\n▶ Starting 10-second test stimulation...")
                print("   (The LED should flash at 40 Hz for 10 seconds)")
                controller.set_duration(10.0)
                if controller.start_stimulation():
                    print("   ✓ Stimulation started!")
                    print("   Waiting for Arduino to complete...")
                    time.sleep(11)  # Wait for it to finish
                    print("   ✓ Test complete")
                else:
                    print("   ✗ Failed to start")
            
            elif choice == "2":
                print("\n▶ Starting continuous stimulation...")
                print("   (Use option 3 to stop)")
                if controller.start_stimulation():
                    print("   ✓ Stimulation started!")
                else:
                    print("   ✗ Failed to start")
            
            elif choice == "3":
                print("\n■ Stopping stimulation...")
                if controller.stop_stimulation():
                    print("   ✓ Stopped")
                else:
                    print("   ✗ Stop command sent (no ACK)")
            
            elif choice == "4":
                try:
                    freq = float(input("   Enter frequency (Hz, 1-100): "))
                    if controller.set_frequency(freq):
                        print(f"   ✓ Frequency set to {freq} Hz")
                    else:
                        print("   ✗ Failed to set frequency")
                except ValueError:
                    print("   ✗ Invalid number")
            
            elif choice == "5":
                try:
                    dur = float(input("   Enter duration (seconds, 1-600): "))
                    if controller.set_duration(dur):
                        print(f"   ✓ Duration set to {dur}s")
                    else:
                        print("   ✗ Failed to set duration")
                except ValueError:
                    print("   ✗ Invalid number")
            
            elif choice == "6":
                print("\n📊 Status:")
                status = controller.get_status()
                if status:
                    print(f"   {status}")
                print(f"   Connected: {controller.connected}")
                print(f"   Stimulating: {controller.stimulating}")
                print(f"   Port: {controller.port_name}")
            
            elif choice == "7":
                print("\n⏹ Disconnecting...")
                controller.disconnect()
                print("   Goodbye!")
                break
            
            else:
                print("   Invalid choice")
    
    except KeyboardInterrupt:
        print("\n\n⏹ Interrupted by user")
        controller.disconnect()
        print("   Disconnected")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        controller.disconnect()
