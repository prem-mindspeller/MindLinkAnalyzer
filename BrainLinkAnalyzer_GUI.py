#!/usr/bin/env python3
"""
MindLink Feature Analysis GUI
Based on the original BrainCompanion but performs feature analysis instead of sending data.
Includes all original sampling, processing, and authentication from the mother code.
"""

import sys, os, time, threading, requests, random
import serial.tools.list_ports
from cushy_serial import CushySerial
import numpy as np
import pandas as pd
import json
from datetime import datetime
import platform
import ssl
import getpass
from collections import deque
import weakref
from typing import Any, Dict, List, Optional

# REAL MINDLINK PARSER - NO DUMMY DATA ALLOWED
from BrainLinkParser.BrainLinkParser import BrainLinkParser

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QRadioButton, QButtonGroup, QDialog, QFormLayout, QLineEdit,
    QDialogButtonBox, QGroupBox, QCheckBox, QTextEdit, QMessageBox, QInputDialog,
    QTabWidget, QComboBox, QSpinBox, QDoubleSpinBox, QProgressBar, QTableWidget,
    QTableWidgetItem, QHeaderView, QSplitter, QFrame, QGridLayout, QFileDialog,
    QSizePolicy
)
from PySide6.QtCore import QTimer, Qt, QSettings, QThread, Signal
from PySide6.QtGui import QIcon, QFont
# Ensure pyqtgraph uses PySide6 binding before import to avoid QWidget type mismatches
import os as _os
try:
    _os.environ.setdefault('PYQTGRAPH_QT_LIB', 'PySide6')
except Exception:
    pass
import pyqtgraph as pg
from scipy.signal import butter, filtfilt, iirnotch, welch, decimate, hilbert
from scipy.integrate import simpson as simps
from scipy.stats import zscore

# Windowed task analysis pipeline modules
# from task_analyzer import TaskAnalyzer
# from event_parser import parse_events
# from task_reporting import render_task_report, render_two_session_agreement
# Optional extra tasks plugin - import dynamically to avoid static resolution errors
try:
    import importlib
    import importlib.util
    if importlib.util.find_spec("extra_tasks") is not None:
        mod = importlib.import_module("extra_tasks")
        EXTRA_TASKS = getattr(mod, "EXTRA_TASKS", {})
    else:
        EXTRA_TASKS = {}
except Exception as e:
    # Non-fatal: continue with empty extra tasks and log a warning
    print(f"Warning: optional module 'extra_tasks' not imported: {e}")
    EXTRA_TASKS = {}

# Import winreg only on Windows
if platform.system() == 'Windows':
    import winreg

# Set up PyQtGraph for better display compatibility
pg.setConfigOption('useOpenGL', False)
pg.setConfigOption('antialias', True)
pg.setConfigOption('background', 'k')
pg.setConfigOption('foreground', 'w')
pg.setConfigOption('crashWarning', True)
pg.setConfigOption('imageAxisOrder', 'row-major')

# Authentication settings from mother code
BACKEND_URLS = {
    "en": "https://en.mindspeller.com/api/cas/token/login",
    "nl": "https://nl.mindspeller.com/api/cas/token/login",
    "local": "http://127.0.0.1:5000/api/cas/token/login"
}

LOGIN_URLS = {
    "en": "https://en.mindspeller.com/api/cas/token/login",
    "nl": "https://nl.mindspeller.com/api/cas/token/login",
    "local": "http://127.0.0.1:5000/api/cas/token/login"
}

# --- Helper to locate asset files ---
def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller."""
    base_path = getattr(sys, '_MEIPASS', os.path.abspath("."))
    return os.path.join(base_path, relative_path)


MODERN_DIALOG_STYLESHEET = """
QDialog {
    background:#f8fafc;
}
QLabel#DialogTitle {
    font-size:18px;
    font-weight:600;
    color:#1f2937;
}
QLabel#DialogSubtitle {
    font-size:13px;
    color:#475569;
}
QLabel#DialogSectionTitle,
QLabel#DialogSectionLabel {
    font-size:13px;
    font-weight:600;
    color:#1f2937;
}
QFrame#DialogCard {
    background:#ffffff;
    border:1px solid #e2e8f0;
    border-radius:12px;
}
QLineEdit,
QComboBox,
QTextEdit {
    font-size:13px;
    padding:8px 10px;
    border:1px solid #cbd5e1;
    border-radius:8px;
    background:#f8fafc;
    color:#1f2937;
}
QLineEdit:focus,
QComboBox:focus,
QTextEdit:focus {
    border-color:#3b82f6;
    background:#ffffff;
}
QLineEdit::placeholder {
    color:#94a3b8;
}
QCheckBox,
QRadioButton {
    font-size:13px;
    color:#1f2937;
    spacing:8px;
}
QDialogButtonBox {
    border-top:1px solid transparent;
}
QDialogButtonBox QPushButton {
    background-color:#2563eb;
    color:#ffffff;
    border-radius:8px;
    padding:8px 18px;
    font-size:13px;
    border:0;
}
QDialogButtonBox QPushButton:hover {
    background-color:#1d4ed8;
}
QDialogButtonBox QPushButton:pressed {
    background-color:#1e40af;
}
QDialogButtonBox QPushButton:disabled {
    background-color:#dbeafe;
    color:#64748b;
}
"""


def apply_modern_dialog_theme(dialog: QDialog) -> None:
    """Apply the refreshed light theme to modal dialogs for UI consistency."""
    dialog.setStyleSheet(MODERN_DIALOG_STYLESHEET)

# Global variables from mother code
BACKEND_URL = None
SERIAL_PORT = None
SERIAL_BAUD = 115200
ALLOWED_HWIDS = []
stop_thread_flag = False
live_data_buffer = []

# Signal processing constants from mother code (corrected to match BrainCompanion_updated.py)
FS = 512
WINDOW_SIZE = 512 
OVERLAP_SIZE = 128
EEG_BANDS = {
    'delta': (0.5, 4),
    'theta': (4, 8),
    'alpha': (8, 12),
    'beta': (12, 30),
    'gamma': (30, 45)
}

# Feature analysis constants
FEATURE_NAMES = [
    'delta_power', 'theta_power', 'alpha_power', 'beta_power', 'gamma_power',
    'delta_relative', 'theta_relative', 'alpha_relative', 'beta_relative', 'gamma_relative',
    'delta_peak_freq', 'theta_peak_freq', 'alpha_peak_freq', 'beta_peak_freq', 'gamma_peak_freq',
    'delta_peak_amp', 'theta_peak_amp', 'alpha_peak_amp', 'beta_peak_amp', 'gamma_peak_amp',
    'alpha_theta_ratio', 'beta_alpha_ratio', 'total_power'
]

# Available cognitive tasks
AVAILABLE_TASKS = {
    'visual_imagery': {
        'name': 'Visual Imagery',
        'description': 'Visualize a familiar place or object in detail',
        'duration': 60,
        'instructions': '🔊 EYES CLOSED TASK - Visualize walking through your home in rich sensory detail.\n\nAudio cues:\n• 1st beep = Read instructions on screen\n• 2nd beep = Close eyes & start visualizing\n• 2 beeps = Task complete, you can stop',
        'phases': ['analyze', 'rest'],
        'phase_structure': [
            {'type': 'cue', 'duration': 8, 'record': False, 'instruction': 'CUE: Visualize walking through your home in rich sensory detail continuously. (Start on beep sound).'},
            {'type': 'task', 'duration': 52, 'record': True, 'instruction': 'IMAGERY: Visualize walking through your home in rich sensory detail continuously.'}
        ]
    },
    'attention_focus': {
        'name': 'Focused Attention',
        'description': 'Focus intensely on breathing or a single point',
        'duration': 60,
        'instructions': '🔊 EYES CLOSED TASK - Focus all attention on your breathing. Count breaths 1–10 and repeat.\n\nAudio cues:\n• 1st beep = Read instructions on screen\n• 2nd beep = Close eyes & start focusing\n• 2 beeps = Task complete, you can stop',
        'phases': ['analyze', 'rest'],
        'phase_structure': [
            {'type': 'cue', 'duration': 8, 'record': False, 'instruction': 'FOCUS: Attend only to breathing. Count breaths 1–10 and restart; gently return if distracted with EYES CLOSED.'},
            {'type': 'task', 'duration': 52, 'record': True, 'instruction': 'FOCUS: Attend only to breathing. Count breaths 1–10 and restart; gently return if distracted with EYES CLOSED.'}
        ]
    },
    'mental_math': {
        'name': 'Mental Math',
        'description': 'Perform mental arithmetic (e.g., count backwards from 200 by 7s)',
        'duration': 60,
        'instructions': '🔊 EYES CLOSED TASK - Count backwards from 200 by 7s: 200, 193, 186, 179...\n\nAudio cues:\n• 1st beep = Read instructions on screen\n• 2nd beep = Close eyes & start counting\n• 2 beeps = Task complete, you can stop',
        'phases': ['analyze', 'rest'],
        'phase_structure': [
            {'type': 'cue', 'duration': 8, 'record': False, 'instruction': 'CUE: Prepare to count backwards from 200 by 7s with your EYES CLOSED.'},
            {'type': 'task', 'duration': 52, 'record': True, 'instruction': 'COUNT: 200, 193, 186, 179... Keep counting backwards by 7s.'}
        ]
    },
    'working_memory': {
        'name': 'Working Memory',
        'description': 'Remember and manipulate a sequence of numbers or letters',
        'duration': 60,
        'instructions': '🔊 EYES CLOSED TASK - Remember this sequence: 3-8-2-9-5-1. Now add 2 to each number mentally.\n\nAudio cues:\n• 1st beep = Read instructions on screen\n• 2nd beep = Close eyes & start calculating\n• 2 beeps = Task complete, you can stop',
        'phases': ['analyze', 'rest'],
        'phase_structure': [
            {'type': 'cue', 'duration': 8, 'record': False, 'instruction': 'CUE: Prepare to remember and manipulate this sequence: 3-8-2-9-5-1. Add 2 to each number with EYES CLOSED.'},
            {'type': 'task', 'duration': 52, 'record': True, 'instruction': 'REMEMBER: 3-8-2-9-5-1. Add 2 to each number: 5-10-4-11-7-3. Keep manipulating the sequence.'}
        ]
    },
    'attention_focus': {
        'name': 'Focused Attention',
        'description': 'Focus intensely on breathing or a single point',
        'duration': 60,
        'instructions': '🔊 EYES CLOSED TASK - Focus all attention on your breathing. Count breaths 1–10 and repeat.\n\nAudio cues:\n• 1st beep = Read instructions on screen\n• 2nd beep = Close eyes & start focusing\n• 2 beeps = Task complete, you can stop',
        'phases': ['analyze', 'rest'],
        'phase_structure': [
            {'type': 'cue', 'duration': 8, 'record': False, 'instruction': 'FOCUS: Attend only to breathing. Count breaths 1–10 and restart; gently return if distracted with EYES CLOSED.'},
            {'type': 'task', 'duration': 52, 'record': True, 'instruction': 'FOCUS: Attend only to breathing. Count breaths 1–10 and restart; gently return if distracted with EYES CLOSED.'}
        ]
    },
    'language_processing': {
        'name': 'Language Processing',
        'description': 'Generate words or sentences following specific rules',
        'duration': 60,
        'instructions': '🔊 EYES CLOSED TASK - Think of as many words as possible that start with the letter "S".\n\nAudio cues:\n• 1st beep = Read instructions on screen\n• 2nd beep = Close eyes & start generating words\n• 2 beeps = Task complete, you can stop',
        'phases': ['analyze', 'rest'],
        'phase_structure': [
            {'type': 'cue', 'duration': 8, 'record': False, 'instruction': 'CUE: Prepare – Silently list distinct "S" words, avoid repeats, keep steady pace with EYES CLOSED.).'},
            {'type': 'task', 'duration': 52, 'record': True, 'instruction': 'GENERATE: Silently list distinct "S" words, avoid repeats, keep steady pace.'}
        ]
    },
    'motor_imagery': {
        'name': 'Motor Imagery',
        'description': 'Imagine performing physical movements without moving',
        'duration': 60,
        'instructions': '🔊 EYES CLOSED TASK - Imagine throwing a ball with your right hand, then left hand, alternating.\n\nAudio cues:\n• 1st beep = Read instructions on screen\n• 2nd beep = Close eyes & start imagining\n• 2 beeps = Task complete, you can stop',
        'phases': ['analyze', 'rest'],
        'phase_structure': [
            {'type': 'cue', 'duration': 8, 'record': False, 'instruction': 'CUE: Prepare to imagine throwing a ball with your right hand, then left hand, alternating with EYES CLOSED.'},
            {'type': 'task', 'duration': 52, 'record': True, 'instruction': 'IMAGINE: Throw a ball with your right hand, then left hand, alternating. Feel the motion vividly.'}
        ]
    },
    'cognitive_load': {
        'name': 'Cognitive Load',
        'description': 'Perform multiple cognitive tasks simultaneously',
        'duration': 60,
        'instructions': '🔊 EYES CLOSED TASK - Count backwards from 50 by 3s while visualizing the numbers in blue.\n\nAudio cues:\n• 1st beep = Read instructions on screen\n• 2nd beep = Close eyes & start task\n• 2 beeps = Task complete, you can stop',
        'phases': ['analyze', 'rest'],
        'phase_structure': [
            {'type': 'cue', 'duration': 8, 'record': False, 'instruction': 'CUE: Prepare to count backwards from 50 by 3s while visualizing each number in blue with EYES CLOSED.'},
            {'type': 'task', 'duration': 52, 'record': True, 'instruction': 'COUNT & VISUALIZE: 50, 47, 44, 41... Count backwards by 3s while seeing each number in blue.'}
        ]
    },
    # --- Added protocol tasks with phase-based timing ---
    'emotion_face': {
    'name': 'Emotion Recognition',
        'description': 'View static emotional face images with timed phases.',
        'duration': 114,  # 6 images × 19s each (8s cue + 11s look+resonate)
        'instructions': '👁️ EYES OPEN TASK - For each face: LOOK & RESONATE with the emotion shown.\n\nAudio cues: 1st beep = Read instructions on screen | 2nd beep = Keep eyes open & start task | 2 beeps = End task',
        'phases': ['analyze', 'rest'],
        'continuous_recording': True,  # Record throughout entire task
        'phase_structure': [
            {'type': 'cue', 'duration': 8, 'record': True, 'instruction': 'CUE: Prepare to LOOK & RESONATE with the upcoming face.'},
            {'type': 'viewing', 'duration': 11, 'record': True, 'media_index': 0, 'instruction': 'LOOK & RESONATE'},
            {'type': 'cue', 'duration': 8, 'record': True, 'instruction': 'CUE: Prepare to LOOK & RESONATE with the upcoming face.'},
            {'type': 'viewing', 'duration': 11, 'record': True, 'media_index': 1, 'instruction': 'LOOK & RESONATE'},
            {'type': 'cue', 'duration': 8, 'record': True, 'instruction': 'CUE: Prepare to observe the upcoming face.'},
            {'type': 'viewing', 'duration': 11, 'record': True, 'media_index': 2, 'instruction': 'LOOK & RESONATE'},
            {'type': 'cue', 'duration': 8, 'record': True, 'instruction': 'CUE: Prepare to observe the upcoming face.'},
            {'type': 'viewing', 'duration': 11, 'record': True, 'media_index': 3, 'instruction': 'LOOK & RESONATE'},
            {'type': 'cue', 'duration': 8, 'record': True, 'instruction': 'CUE: Prepare to observe the upcoming face.'},
            {'type': 'viewing', 'duration': 11, 'record': True, 'media_index': 4, 'instruction': 'LOOK & RESONATE'},
            {'type': 'cue', 'duration': 8, 'record': True, 'instruction': 'CUE: Prepare to observe the upcoming face.'},
            {'type': 'viewing', 'duration': 11, 'record': True, 'media_index': 5, 'instruction': 'LOOK & RESONATE'}
        ],
        'media': {
            'images': [
                'emo_face_01.png', 'emo_face_02.png', 'emo_face_03.png',
                'emo_face_04.png', 'emo_face_05.png', 'emo_face_06.png'
            ],
            'videos': []
        }
    },
    'diverse_thinking': {
    'name': 'Creative Fluency',
        'description': 'Divergent thinking task with timed phases.',
        'duration': 96,  # 2 prompts × 48s each (8s get ready + 10s cue + 30s thinking)
        'instructions': '👁️ EYES OPEN TASK - Read the prompt, then think of creative and unusual uses.\n\nAudio cues: 1st beep = Read instructions on screen | 2nd beep = Keep eyes open & start thinking | 2 beeps = End task',
        'phases': ['analyze', 'rest'],
        'phase_structure': [
            {'type': 'get_ready', 'duration': 8, 'record': False, 'instruction': 'Get ready for creative thinking...'},
            {'type': 'cue', 'duration': 10, 'record': False, 'prompt_index': 0},
            {'type': 'thinking', 'duration': 30, 'record': True, 'prompt_index': 0},
            {'type': 'get_ready', 'duration': 8, 'record': False, 'instruction': 'Get ready for next prompt...'},
            {'type': 'cue', 'duration': 10, 'record': False, 'prompt_index': 1},
            {'type': 'thinking', 'duration': 30, 'record': True, 'prompt_index': 1}
        ],
        'media': {
            'type': 'text_prompts',
            'prompts': [
                {
                    'title': 'CREATIVE USES - PAPERCLIP',
                    'text': 'Think of as many creative and unusual uses for a PAPERCLIP as you can.\n\nGo beyond the obvious uses - be creative and imaginative!',
                    'duration': 30
                },
                {
                    'title': 'CREATIVE USES - ARTIFICIAL INTELLIGENCE',
                    'text': 'Think of as many creative and innovative uses for ARTIFICIAL INTELLIGENCE as you can.\n\nConsider both current and future possibilities!',
                    'duration': 30
                }
            ]
        }
    },
    'reappraisal': {
    'name': 'Perspective Shift',
        'description': 'Cognitive reappraisal task with timed phases.',
        'duration': 96,  # 2 scenarios × 48s each (8s get ready + 10s cue + 30s thinking)
        'instructions': '👁️ EYES OPEN TASK - Read the scenario and follow the specific thinking instructions.\n\nAudio cues: 1st beep = Read instructions on screen | 2nd beep = Keep eyes open & start task | 2 beeps = End task',
        'phases': ['analyze', 'rest'],
        'phase_structure': [
            {'type': 'get_ready', 'duration': 8, 'record': False, 'instruction': 'Get ready for thinking task...'},
            {'type': 'cue', 'duration': 10, 'record': False, 'prompt_index': 0},
            {'type': 'thinking', 'duration': 30, 'record': True, 'prompt_index': 0},
            {'type': 'get_ready', 'duration': 8, 'record': False, 'instruction': 'Get ready for next scenario...'},
            {'type': 'cue', 'duration': 10, 'record': False, 'prompt_index': 1},
            {'type': 'thinking', 'duration': 30, 'record': True, 'prompt_index': 1}
        ],
        'media': {
            'type': 'text_prompts',
            'prompts': [
                {
                    'title': 'THINK POSITIVE',
                    'scenario': 'Feedback from a close friend',
                    'instruction': 'Try to see this situation in a positive light. What good could come from this? What are the silver linings?',
                    'duration': 30
                },
                {
                    'title': 'FOCUS ON NEGATIVES',
                    'scenario': 'Going to miss a flight',
                    'instruction': 'Think about what went wrong with this situation. Focus on the problems and negative consequences.',
                    'duration': 30
                }
            ]
        }
    },
    'curiosity': {
    'name': 'Curiosity Reveal',
        'description': 'Curiosity task with reveal timing.',
        'duration': 45,  # 8s get ready + 2s cue + 2s wait + 33s video
        'instructions': '👁️ EYES OPEN TASK - Watch the video reveal with full attention.\n\nAudio cues: 1st beep = Read instructions on screen | 2nd beep = Keep eyes open & video starts | 2 beeps = End task',
        'phases': ['analyze', 'rest'],
        'phase_structure': [
            {'type': 'get_ready', 'duration': 8, 'record': False, 'instruction': 'Get ready for video reveal...'},
            {'type': 'cue', 'duration': 2, 'record': False, 'instruction': 'Video starting soon...'},
            {'type': 'wait', 'duration': 2, 'record': True, 'instruction': 'Video starting...'},
            {'type': 'video', 'duration': 33, 'record': True, 'media_file': 'curiosity_clip_01.mp4'}
        ],
        'media': {
            # Placeholders; ensure files exist in assets/ or replace with available ones
            'images': ['curiosity_card_back.png'],
            'videos': ['curiosity_clip_01.mp4']
        }
    },
    # --- Lifestyle pathway tasks ---
    'num_form': {
        'name': 'Numerical Preference',
        'description': 'Evaluate aesthetic preference for numbers vs forms with balanced look phases.',
        'duration': 60,
        'instructions': (
            '👁️ EYES OPEN TASK\n\n'
            'NUMBERS: Wait for the countdown, then LOOK for the numbers. Keep your gaze steady and minimize movement.\n'
            'FORMS: Wait for the countdown, then LOOK for the shapes. Keep your gaze steady and minimize movement.\n\n'
            'Audio cues: 1 beep = Start task | 1 smooth beep = Phase change | 2 beeps = End task'
        ),
        'phases': ['analyze', 'rest'],
        'continuous_recording': True,
        'phase_structure': [
            {'type': 'get_ready', 'duration': 8, 'record': False, 'instruction': 'Get ready...'},
            {'type': 'cue', 'duration': 8, 'record': False, 'instruction': 'NUMBERS'},
            {'type': 'viewing', 'duration': 20, 'record': True, 'media_file': 'NUM_FORM.png'},
            {'type': 'cue', 'duration': 8, 'record': False, 'instruction': 'FORMS'},
            {'type': 'viewing', 'duration': 20, 'record': True, 'media_file': 'NUM_FORM.png'},
            {'type': 'rest', 'duration': 2, 'record': False, 'instruction': 'Rest.'}
        ],
        'media': {
            'images': ['NUM_FORM.png'],
            'videos': []
        }
    },
    'order_surprise': {
        'name': 'Order & Surprise',
        'description': 'Evaluate aesthetic response to ORDER vs SURPRISE with balanced look phases.',
        'duration': 60,
        'instructions': (
            '👁️ EYES OPEN TASK\n\n'
            'ORDER: Wait for the countdown, then COUNT symmetrical/normal shapes. Keep your gaze steady and minimize movement.\n'
            'SURPRISE: Wait for the countdown, then COUNT non-symmetrical/abnormal shapes. Keep your gaze steady and minimize movement.\n\n'
            'Audio cues: 1 beep = Start task | 1 smooth beep = Phase change | 2 beeps = End task'
        ),
        'phases': ['analyze', 'rest'],
        'continuous_recording': True,
        'phase_structure': [
            {'type': 'get_ready', 'duration': 8, 'record': False, 'instruction': 'Get ready...'},
            {'type': 'cue', 'duration': 8, 'record': False, 'instruction': 'ORDER'},
            {'type': 'viewing', 'duration': 20, 'record': True, 'media_file': 'ORDER_SURPRISE.png'},
            {'type': 'cue', 'duration': 8, 'record': False, 'instruction': 'SURPRISE'},
            {'type': 'viewing', 'duration': 20, 'record': True, 'media_file': 'ORDER_SURPRISE.png'},
            {'type': 'rest', 'duration': 2, 'record': False, 'instruction': 'Rest.'}
        ],
        'media': {
            'images': ['ORDER_SURPRISE.png'],
            'videos': []
        }
    },
    '40hz_stimulation': {
        'name': '40Hz Stimulation',
        'description': '40Hz visual stimulation task with resting baseline - Multi-channel only',
        'duration': 285,  # 5s cue + 60s rest + 5s cue + 150s task + 5s cue + 60s rest
        'instructions': (
            '👁️ EYES OPEN TASK - Gamma entrainment protocol\n\n'
            'Phase 1 (5s): PREPARATION - Get ready for resting state.\n'
            'Phase 2 (60s): RESTING STATE - Relax and calm yourself. Do nothing.\n'
            'Phase 3 (5s): PREPARATION - Get ready for the task phase.\n'
            'Phase 4 (150s): STIMULATION - Look at the white box. Focus on the red LED.\n'
            'Phase 5 (5s): PREPARATION - Get ready for resting state.\n'
            'Phase 6 (60s): RESTING STATE - Relax and calm yourself again.\n\n'
            'Audio cues: 1 beep = Start | 1 smooth beep = Phase change | 2 beeps = End'
        ),
        'phases': ['analyze', 'rest'],
        'continuous_recording': True,
        'multichannel_only': True,  # Multi-channel devices only (ANT Neuro)
        'hide_countdown': True,  # Don't show countdown timer for eyes-open tasks
        'phase_structure': [
            {'type': 'cue', 'duration': 5, 'record': False, 'instruction': 'PREPARATION (Phase 1 of 6)\n\nGet ready for resting state...\n\nRelax and calm yourself.'},
            {'type': 'rest', 'duration': 60, 'record': True, 'instruction': 'RESTING STATE (Phase 2 of 6)\n\nTry to relax and calm yourself.\nDo nothing.\n\n60 seconds'},
            {'type': 'cue', 'duration': 5, 'record': False, 'instruction': 'PREPARATION (Phase 3 of 6)\n\nGet ready for the task phase...\n\nThe stimulation will start soon.'},
            {'type': 'task', 'duration': 150, 'record': True, 'instruction': '40Hz STIMULATION (Phase 4 of 6)\n\nLook at the white box to your right.\nStay calm and focused on the red LED\nin the center of the white box.\n\n150 seconds (2.5 minutes)'},
            {'type': 'cue', 'duration': 5, 'record': False, 'instruction': 'PREPARATION (Phase 5 of 6)\n\nGet ready for resting state...\n\nRelax and calm yourself.'},
            {'type': 'rest', 'duration': 60, 'record': True, 'instruction': 'RESTING STATE (Phase 6 of 6)\n\nTry to relax and calm yourself again.\nDo nothing.\n\n60 seconds'}
        ],
        'media': {
            'images': [],
            'videos': []
        }
    }
}

# Merge in any extra protocol tasks
if EXTRA_TASKS:
    try:
        AVAILABLE_TASKS.update(EXTRA_TASKS)
    except Exception:
        pass

# Signal processing functions from mother code
def butter_lowpass_filter(data, cutoff, fs, order=2):
    nyq = 0.5 * fs
    normal_cutoff = cutoff / nyq
    b, a = butter(order, normal_cutoff, btype='low', analog=False)
    return filtfilt(b, a, data)

def bandpass_filter(data, lowcut=1.0, highcut=45.0, fs=512, order=2):
    nyq = 0.5 * fs
    b, a = butter(order, [lowcut/nyq, highcut/nyq], btype='band')
    return filtfilt(b, a, data)

def notch_filter(data, fs, notch_freq=60.0, quality_factor=30.0):
    freq = notch_freq/(fs/2)
    b, a = iirnotch(freq, quality_factor)
    return filtfilt(b, a, data)

def compute_psd(data, fs):
    freqs, psd = welch(data, fs=fs, nperseg=WINDOW_SIZE, noverlap=OVERLAP_SIZE)
    return freqs, psd

def bandpower(psd, freqs, band):
    low, high = EEG_BANDS[band]
    idx = (freqs >= low) & (freqs <= high)
    return simps(psd[idx], dx=freqs[1] - freqs[0]) if np.any(idx) else 0

def remove_eye_blink_artifacts(data, window=10):
    """Remove eye blink artifacts from EEG data"""
    clean = data.copy()
    adaptive_threshold = np.mean(data) + 3 * np.std(data)
    idx = np.where(np.abs(data) > adaptive_threshold)[0]
    for i in idx:
        start = max(0, i - window)
        end = min(len(data), i + window)
        local_window = np.delete(data[start:end], np.where(np.abs(data[start:end]) > adaptive_threshold))
        if len(local_window) > 0:
            clean[i] = np.median(local_window)
        else:
            clean[i] = np.median(data)
    return clean


def check_signal_legitimacy(data_window, min_variance=0.05, max_diff_std=0.1, max_identical_fraction=0.02):
    """Perform quick heuristic checks to determine if the incoming EEG window looks legitimate.

    Returns a dict with flags and short messages. Heuristics used:
      - low_variance: variance below min_variance (flatline / disconnected)
      - regular_steps: very low std of successive differences (possible synthetic/demo)
      - too_many_identical: many repeated identical values (clipping or synthetic)
    """
    metrics = {}
    arr = np.array(data_window)
    metrics['variance'] = float(np.var(arr)) if arr.size > 0 else 0.0
    metrics['std_of_diffs'] = float(np.std(np.diff(arr))) if arr.size > 1 else 0.0
    # Fraction of identical samples (exact equality)
    if arr.size > 0:
        unique_count = len(np.unique(arr))
        metrics['identical_fraction'] = 1.0 - (unique_count / float(arr.size))
    else:
        metrics['identical_fraction'] = 1.0

    flags = {
        'low_variance': metrics['variance'] < min_variance,
        'regular_steps': metrics['std_of_diffs'] < max_diff_std,
        'too_many_identical': metrics['identical_fraction'] > max_identical_fraction
    }

    messages = []
    if flags['low_variance']:
        messages.append('Low variance - possible disconnected/flatline signal')
    if flags['regular_steps']:
        messages.append('Highly regular sample-to-sample steps - possible synthetic/demo data')
    if flags['too_many_identical']:
        messages.append('Many identical values - possible clipping or artificial data')

    return {'flags': flags, 'metrics': metrics, 'messages': messages}


def is_signal_noisy(data_window, fs=512, high_freq_threshold=30.0, high_freq_ratio_thresh=0.7):
    """Estimate whether the window is dominated by high-frequency noise.

    Simple heuristic: compute PSD and compare power above `high_freq_threshold` to total power.
    Returns (is_noisy: bool, details: dict)
    
    Note: Threshold increased to 0.7 (70%) to reduce false positives from normal EEG artifacts.
    """
    arr = np.array(data_window)
    details = {}
    if arr.size < 4:
        details['reason'] = 'too_short'
        details['high_freq_ratio'] = 0.0
        return False, details

    try:
        freqs, psd = compute_psd(arr, fs)
        total = np.trapz(psd, freqs) if psd.size > 0 else 0.0
        mask = freqs >= high_freq_threshold
        high_power = np.trapz(psd[mask], freqs[mask]) if np.any(mask) else 0.0
        ratio = float(high_power / (total + 1e-12))
        details['total_power'] = float(total)
        details['high_power'] = float(high_power)
        details['high_freq_ratio'] = ratio
        details['freq_max'] = float(freqs[np.argmax(psd)]) if psd.size > 0 else 0.0
        is_noisy = ratio > high_freq_ratio_thresh
        return is_noisy, details
    except Exception as e:
        details['error'] = str(e)
        return False, details

def detect_brainlink():
    """Device detection from mother code with enhanced logging"""
    ports = serial.tools.list_ports.comports()
    print(f"Scanning {len(ports)} available ports...")
    
    # If user-specific HWIDs are provided, use them first
    if ALLOWED_HWIDS:
        print(f"Looking for authorized HWIDs: {ALLOWED_HWIDS}")
        for port in ports:
            print(f"Checking port: {port.device} - {port.description}")
            if hasattr(port, 'hwid'):
                print(f"  HWID: {port.hwid}")
                if any(hw in port.hwid for hw in ALLOWED_HWIDS):
                    print(f"✓ Found authorized MindLink device: {port.device}")
                    return port.device
            else:
                print(f"  No HWID attribute found")
    
    # Fallback to platform-specific detection
    print("Falling back to platform-specific detection...")
    if platform.system() == 'Windows':
        BRAINLINK_SERIALS = ("5C361634682F", "5C3616327E59", "5C3616346938", "5C3616346838", "5C36163468D3", "5C3616327C21", "5C36163468D3")
        for port in ports:
            if hasattr(port, 'hwid'):
                if any(hw in port.hwid for hw in BRAINLINK_SERIALS):
                    print(f"✓ Found MindLink device by serial: {port.device}")
                    return port.device
    elif platform.system() == 'Darwin':
        for port in ports:
            if any(id in port.description.lower() for id in ["brainlink", "neurosky", "ftdi", "silabs", "ch340"]):
                print(f"✓ Found MindLink device by description: {port.device}")
                return port.device
            if port.device.startswith("/dev/tty.usbserial"):
                print(f"✓ Found MindLink device by device name: {port.device}")
                return port.device
            if port.device.startswith("/dev/tty.usbmodem"):
                print(f"✓ Found MindLink device by device name: {port.device}")
                return port.device
    
    print("✗ No MindLink device found")
    print("Available ports:")
    for port in ports:
        hwid_info = f" (HWID: {port.hwid})" if hasattr(port, 'hwid') else ""
        print(f"  - {port.device}: {port.description}{hwid_info}")
    
    return None

# Data collection callbacks from mother code
def onRaw(raw):
    global live_data_buffer
    
    # CRITICAL VALIDATION: Detect if we're getting dummy data patterns
    # Check for suspicious patterns that indicate dummy data generation
    if hasattr(onRaw, '_last_values'):
        onRaw._last_values.append(raw)
        if len(onRaw._last_values) > 10:
            onRaw._last_values = onRaw._last_values[-10:]
            
        # Check for unrealistic patterns (like perfect sine waves from dummy generator)
        if len(onRaw._last_values) >= 10:
            values = np.array(onRaw._last_values)
            # Check for suspiciously regular patterns
            diffs = np.diff(values)
            if np.std(diffs) < 0.1 or np.all(np.abs(diffs) < 0.01):
                print("WARNING: Detected potentially artificial/dummy data patterns!")
                print("Please ensure you're connected to a REAL MindLink device!")
    else:
        onRaw._last_values = [raw]
    
    live_data_buffer.append(raw)
    # CRITICAL FIX: Trim buffer IN-PLACE to prevent unbounded growth
    # Using slice assignment del[:] to modify the SAME list object
    # This ensures all modules referencing live_data_buffer see the trimmed version
    if len(live_data_buffer) > 1024:  # Keep ~2 seconds of data at 512 Hz
        del live_data_buffer[:-1024]  # Delete oldest samples, keep last 1024
    
    # Also feed data to feature engine if GUI is running
    if hasattr(onRaw, 'feature_engine') and onRaw.feature_engine:
        onRaw.feature_engine.add_data(raw)
    
    # Show processed values in console every 50 samples (unless suppressed by enhanced GUI)
    if len(live_data_buffer) % 50 == 0 and not getattr(onRaw, '_suppress_console', False):
        # print(f"\n=== EEG ANALYZER CONSOLE OUTPUT ===")
        # print(f"Buffer size: {len(live_data_buffer)} samples")
        # print(f"Latest raw value: {raw:.1f} µV")
        
        # Process the data if we have enough samples
        if len(live_data_buffer) >= 512:
            try:
                # Get recent data for analysis
                data = np.array(live_data_buffer[-512:])
                
                # Apply artifact removal before filtering (matching BrainCompanion_updated.py)
                cleaned_data = remove_eye_blink_artifacts(data)
                
                # Apply filters with correct sampling rate
                data_notched = notch_filter(cleaned_data, 512, notch_freq=50.0, quality_factor=30.0)
                filtered = bandpass_filter(data_notched, lowcut=1.0, highcut=45.0, fs=512, order=2)
                
                # Compute basic statistics
                # print(f"Filtered data range: {np.min(filtered):.1f} to {np.max(filtered):.1f} µV")
                # print(f"Mean: {np.mean(filtered):.1f} µV, Std: {np.std(filtered):.1f} µV")
                
                # Compute power spectral density
                freqs, psd = compute_psd(filtered, 512)
                
                # Total EEG power via variance of the signal (matching BrainCompanion_updated.py)
                total_power = np.var(filtered)
                
                # Calculate band powers
                # print(f"EEG BAND POWERS:")
                for band_name, (low, high) in EEG_BANDS.items():
                    power = bandpower(psd, freqs, band_name)
                    relative = power / total_power if total_power > 0 else 0
                    # print(f"  {band_name.upper():5}: {power:8.2f} µV² ({relative:6.1%})")
                
                # Calculate ratios
                alpha_power = bandpower(psd, freqs, 'alpha')
                theta_power = bandpower(psd, freqs, 'theta')
                beta_power = bandpower(psd, freqs, 'beta')
                
                alpha_theta_ratio = alpha_power / (theta_power + 1e-10)
                beta_alpha_ratio = beta_power / (alpha_power + 1e-10)
                
                # print(f"RATIOS:")
                # print(f"  Alpha/Theta: {alpha_theta_ratio:.2f}")
                # print(f"  Beta/Alpha:  {beta_alpha_ratio:.2f}")
                # print(f"  Total Power: {total_power:.2f} µV²")
                
                # Mental state interpretation
                alpha_rel = alpha_power / total_power if total_power > 0 else 0
                theta_rel = theta_power / total_power if total_power > 0 else 0
                beta_rel = beta_power / total_power if total_power > 0 else 0
                # Run additional signal legitimacy and noise checks
                try:
                    recent_window = filtered[-512:] if len(filtered) >= 512 else filtered
                    legitimacy = check_signal_legitimacy(recent_window)
                    noisy, noise_details = is_signal_noisy(recent_window, fs=512)
                    onRaw._last_check = {'legitimacy': legitimacy, 'is_noisy': noisy, 'noise_details': noise_details}
                    # Print concise warnings so users see issues in console
                    if legitimacy['messages']:
                        print("SIGNAL WARNING:", "; ".join(legitimacy['messages']))
                    if noisy:
                        print(f"SIGNAL WARNING: High-frequency noise detected (ratio={noise_details.get('high_freq_ratio',0):.2f})")
                except Exception as e:
                    print(f"Signal checks failed: {e}")

                # print(f"MENTAL STATE INTERPRETATION:")
                # if alpha_rel > 0.3:
                #     print(f"  → High alpha activity - relaxed, eyes closed state")
                # elif beta_rel > 0.3:
                #     print(f"  → High beta activity - alert, focused state")
                # elif theta_rel > 0.3:
                #     print(f"  → High theta activity - drowsy or meditative state")
                # else:
                #     print(f"  → Mixed activity - transitional state")
                
                # print(f"===================================\n")
                
            except Exception as e:
                print(f"Analysis error: {e}")
        else:
            print(f"Need {512 - len(live_data_buffer)} more samples for analysis")
            print(f"===================================\n")

def onEEG(data):
    print("EEG -> attention:", data.attention, "meditation:", data.meditation)

def onExtendEEG(data):
    try:
        battery_val = getattr(data, 'battery', None)
        firmware = getattr(data, 'version', None)
        print("Extended EEG -> battery:", battery_val, "version:", firmware)
    except Exception:
        print("Extended EEG packet received")

    window_ref = None
    if 'BrainLinkAnalyzerWindow' in globals():
        try:
            window_ref = getattr(BrainLinkAnalyzerWindow, '_active_window', None)
        except Exception:
            window_ref = None
    if window_ref:
        try:
            window = window_ref()
        except Exception:
            window = None
        if window is not None:
            try:
                window.handle_extended_eeg_from_packet(data)
            except Exception:
                pass

def onGyro(x, y, z):
    print(f"Gyro -> x={x}, y={y}, z={z}")

def onRR(rr1, rr2, rr3):
    print(f"RR -> rr1={rr1}, rr2={rr2}, rr3={rr3}")

def run_brainlink(serial_obj):
    """MindLink thread function from mother code"""
    global stop_thread_flag
    parser = BrainLinkParser(onEEG, onExtendEEG, onGyro, onRR, onRaw)
    
    print("MindLink thread started")

    @serial_obj.on_message()
    def handle_serial_message(msg: bytes):
        print(f"Received message: {len(msg)} bytes")
        parser.parse(msg)

    try:
        serial_obj.open()
        print(f"Opened {SERIAL_PORT} at {SERIAL_BAUD} baud.")
    except Exception as e:
        print(f"Failed to open serial port: {e}")
        return
        
    try:
        while not stop_thread_flag:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Exiting MindLink thread (KeyboardInterrupt).")
    finally:
        if serial_obj.is_open:
            serial_obj.close()
        print("Serial closed. Thread exiting.")

# --- OS Selection Dialog from mother code ---
class OSSelectionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Your Operating System")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setMinimumWidth(360)

        # Determine default based on auto-detection
        if sys.platform.startswith("win"):
            default_os = "Windows"
        elif sys.platform.startswith("darwin"):
            default_os = "macOS"
        else:
            default_os = "Windows"

        self.selected_os = default_os

        self.radio_windows = QRadioButton("Windows")
        self.radio_macos = QRadioButton("macOS")
        if default_os == "Windows":
            self.radio_windows.setChecked(True)
        else:
            self.radio_macos.setChecked(True)

        title_label = QLabel("Choose your Operating System (OS)")
        title_label.setObjectName("DialogTitle")

        subtitle_label = QLabel("Pick the OS that matches your MindLink setup.")
        subtitle_label.setObjectName("DialogSubtitle")

        card = QFrame()
        card.setObjectName("DialogCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(10)

        prompt_label = QLabel("Please select your OS:")
        prompt_label.setObjectName("DialogSectionTitle")
        card_layout.addWidget(prompt_label)
        card_layout.addWidget(self.radio_windows)
        card_layout.addWidget(self.radio_macos)
        card_layout.addStretch()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        ok_button = buttons.button(QDialogButtonBox.Ok)
        cancel_button = buttons.button(QDialogButtonBox.Cancel)
        if ok_button:
            ok_button.setText("Continue")
            ok_button.setDefault(True)
        if cancel_button:
            cancel_button.setText("Cancel")

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addWidget(card)
        layout.addWidget(buttons, alignment=Qt.AlignRight)

        self.setLayout(layout)
        apply_modern_dialog_theme(self)

    def get_selected_os(self):
        if self.radio_windows.isChecked():
            return "Windows"
        else:
            return "macOS"

# --- Login Dialog from mother code ---
class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sign in to MindLink")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        try:
            self.setWindowIcon(QIcon(resource_path("assets/favicon.ico")))
        except:
            pass
        self.setMinimumWidth(380)
        self.settings = QSettings("MindLink", "FeatureAnalyzer")
        
        self.username_edit = QLineEdit()
        saved_username = self.settings.value("username", "")
        self.username_edit.setText(saved_username)
        self.username_edit.setPlaceholderText("you@example.com")
        self.username_edit.setClearButtonEnabled(True)
        
        self.password_edit = QLineEdit()
        saved_password = self.settings.value("password", "")
        self.password_edit.setText(saved_password)
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setPlaceholderText("Password")
        self.password_edit.setClearButtonEnabled(True)
        
        # Add an eye icon action to toggle password visibility
        self.eye_visible = False
        try:
            self.eye_action = self.password_edit.addAction(QIcon(resource_path("assets/eye-off.png")), QLineEdit.TrailingPosition)
            self.eye_action.triggered.connect(self.toggle_password_visibility)
            self.eye_action.setToolTip("Show password")
        except:
            pass
        
        self.remember_checkbox = QCheckBox("Keep me signed in")
        self.remember_checkbox.setTristate(False)
        if saved_username:
            self.remember_checkbox.setChecked(True)
        
        title_label = QLabel("Welcome!")
        title_label.setObjectName("DialogTitle")

        subtitle_label = QLabel("Use your Mindspeller credentials to continue.")
        subtitle_label.setObjectName("DialogSubtitle")

        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignLeft)
        form_layout.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        form_layout.setHorizontalSpacing(14)
        form_layout.setVerticalSpacing(14)

        username_label = QLabel("Username")
        username_label.setObjectName("DialogSectionLabel")
        password_label = QLabel("Password")
        password_label.setObjectName("DialogSectionLabel")

        form_layout.addRow(username_label, self.username_edit)
        form_layout.addRow(password_label, self.password_edit)

        form_card = QFrame()
        form_card.setObjectName("DialogCard")
        card_layout = QVBoxLayout(form_card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(12)
        card_layout.addLayout(form_layout)
        card_layout.addWidget(self.remember_checkbox)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        ok_button = buttons.button(QDialogButtonBox.Ok)
        cancel_button = buttons.button(QDialogButtonBox.Cancel)
        if ok_button:
            ok_button.setText("Sign in")
            ok_button.setDefault(True)
        if cancel_button:
            cancel_button.setText("Cancel")
        
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addWidget(form_card)
        layout.addWidget(buttons, alignment=Qt.AlignRight)
        self.setLayout(layout)

        apply_modern_dialog_theme(self)
    
    def toggle_password_visibility(self):
        if self.eye_visible:
            self.password_edit.setEchoMode(QLineEdit.Password)
            try:
                self.eye_action.setIcon(QIcon(resource_path("assets/eye-off.png")))
                self.eye_action.setToolTip("Show password")
            except:
                pass
            self.eye_visible = False
        else:
            self.password_edit.setEchoMode(QLineEdit.Normal)
            try:
                self.eye_action.setIcon(QIcon(resource_path("assets/eye.png")))
                self.eye_action.setToolTip("Hide password")
            except:
                pass
            self.eye_visible = True
    
    def get_credentials(self):
        if self.remember_checkbox.isChecked():
            self.settings.setValue("username", self.username_edit.text())
            self.settings.setValue("password", self.password_edit.text())
        else:
            self.settings.remove("username")
            self.settings.remove("password")
        return self.username_edit.text(), self.password_edit.text()

# --- Feature Analysis Engine ---
class FeatureAnalysisEngine:
    def __init__(self):
        self.fs = 512  # Corrected sampling rate
        self.window_size = 1.0
        self.overlap = 0.5
        self.window_samples = int(self.window_size * self.fs)
        
        # Data buffers
        self.raw_buffer = deque(maxlen=self.fs * 10)
        self.filtered_buffers = {band: deque(maxlen=self.fs * 10) for band in EEG_BANDS}
        self.power_buffers = {band: deque(maxlen=self.fs * 10) for band in EEG_BANDS}
        
        # Calibration data storage
        self.calibration_data = {
            'eyes_closed': {'features': [], 'timestamps': []},
            'eyes_open': {'features': [], 'timestamps': []},
            'task': {'features': [], 'timestamps': []}
        }
        
        # Current state
        self.current_state = 'idle'
        self.current_task = None
        self.state_start_time = None
        
        # Analysis results
        self.baseline_stats = {}
        self.analysis_results = {}
        
        # Real-time features
        self.latest_features = {}
    
    def reset_session(self):
        """Clear all accumulated data for new session"""
        # Clear data buffers
        self.raw_buffer.clear()
        for band in self.filtered_buffers:
            self.filtered_buffers[band].clear()
        for band in self.power_buffers:
            self.power_buffers[band].clear()
        
        # Clear calibration data
        self.calibration_data = {
            'eyes_closed': {'features': [], 'timestamps': []},
            'eyes_open': {'features': [], 'timestamps': []},
            'task': {'features': [], 'timestamps': []}
        }
        
        # Reset state
        self.current_state = 'idle'
        self.current_task = None
        self.state_start_time = None
        
        # Clear analysis results
        self.baseline_stats = {}
        self.analysis_results = {}
        self.latest_features = {}
        
        print("✓ Feature engine session reset complete")
        
    def add_data(self, new_data):
        """Add new EEG data and process it"""
        if np.isscalar(new_data):
            new_data = np.array([new_data])
        else:
            new_data = np.array(new_data)
        
        self.raw_buffer.extend(new_data)
        
        # Process if we have enough data
        if len(self.raw_buffer) >= self.window_samples:
            window_data = np.array(list(self.raw_buffer)[-self.window_samples:])
            features = self.extract_features(window_data)
            
            # Store latest features
            self.latest_features = features
            
            # Store based on current state
            if self.current_state in ['eyes_closed', 'eyes_open', 'task']:
                self.calibration_data[self.current_state]['features'].append(features)
                self.calibration_data[self.current_state]['timestamps'].append(time.time())
            
            return features
        return None
    
    def extract_features(self, window_data):
        """Extract comprehensive features from EEG data"""
        features = {}
        
        # Remove DC component
        window_data = window_data - np.mean(window_data)
        
        # Apply notch filter for line noise
        try:
            window_data = notch_filter(window_data, self.fs, notch_freq=50.0)
        except:
            pass
        
        # Compute PSD
        freqs, psd = compute_psd(window_data, self.fs)
        
        # Total EEG power via variance of the signal (matching BrainCompanion_updated.py)
        total_power = np.var(window_data)
        
        # Calculate band powers
        band_powers = {}
        for band_name in EEG_BANDS:
            power = bandpower(psd, freqs, band_name)
            band_powers[band_name] = power
            features[f'{band_name}_power'] = power
            
            # Relative power
            rel_power = power / total_power if total_power > 0 else 0
            features[f'{band_name}_relative'] = rel_power
            
            # Peak frequency and amplitude
            low, high = EEG_BANDS[band_name]
            band_mask = (freqs >= low) & (freqs <= high)
            if np.any(band_mask):
                band_freqs = freqs[band_mask]
                band_psd = psd[band_mask]
                
                if len(band_psd) > 0:
                    peak_idx = np.argmax(band_psd)
                    features[f'{band_name}_peak_freq'] = band_freqs[peak_idx]
                    features[f'{band_name}_peak_amp'] = band_psd[peak_idx]
                else:
                    features[f'{band_name}_peak_freq'] = (low + high) / 2
                    features[f'{band_name}_peak_amp'] = 0
            else:
                features[f'{band_name}_peak_freq'] = (low + high) / 2
                features[f'{band_name}_peak_amp'] = 0
        
        # Compute ratios
        features['alpha_theta_ratio'] = band_powers.get('alpha', 0) / (band_powers.get('theta', 0) + 1e-10)
        features['beta_alpha_ratio'] = band_powers.get('beta', 0) / (band_powers.get('alpha', 0) + 1e-10)
        features['total_power'] = total_power
        
        return features
    
    def start_calibration_phase(self, phase_name, task_type=None):
        """Start calibration phase"""
        self.current_state = phase_name
        self.current_task = task_type
        self.state_start_time = time.time()
        
        # Clear existing data
        self.calibration_data[phase_name]['features'] = []
        self.calibration_data[phase_name]['timestamps'] = []
        
        print(f"Started calibration phase: {phase_name}")
        if task_type:
            print(f"Task: {AVAILABLE_TASKS[task_type]['name']}")
            print(f"Instructions: {AVAILABLE_TASKS[task_type]['instructions']}")
    
    def stop_calibration_phase(self):
        """Stop calibration phase"""
        if self.current_state != 'idle':
            duration = time.time() - self.state_start_time
            num_features = len(self.calibration_data[self.current_state]['features'])
            
            print(f"Stopped calibration phase: {self.current_state}")
            print(f"Duration: {duration:.1f}s, Features collected: {num_features}")
            
            self.current_state = 'idle'
            self.current_task = None
            self.state_start_time = None
    
    def compute_baseline_statistics(self):
        """Compute baseline statistics"""
        baseline_features = []
        baseline_features.extend(self.calibration_data['eyes_closed']['features'])
        baseline_features.extend(self.calibration_data['eyes_open']['features'])
        
        if len(baseline_features) == 0:
            return
        
        df = pd.DataFrame(baseline_features)
        self.baseline_stats = {}
        
        for feature in FEATURE_NAMES:
            if feature in df.columns:
                values = df[feature].values
                self.baseline_stats[feature] = {
                    'mean': np.mean(values),
                    'std': np.std(values),
                    'min': np.min(values),
                    'max': np.max(values),
                    'median': np.median(values),
                    'q25': np.percentile(values, 25),
                    'q75': np.percentile(values, 75)
                }
        
        print(f"Baseline statistics computed for {len(self.baseline_stats)} features")
    
    def analyze_task_data(self):
        """Analyze task data against baseline"""
        if not self.baseline_stats:
            return
        
        task_features = self.calibration_data['task']['features']
        if len(task_features) == 0:
            return
        
        task_df = pd.DataFrame(task_features)
        self.analysis_results = {}
        
        for feature in FEATURE_NAMES:
            if feature in task_df.columns and feature in self.baseline_stats:
                task_values = task_df[feature].values
                baseline_mean = self.baseline_stats[feature]['mean']
                baseline_std = self.baseline_stats[feature]['std']
                
                z_scores = (task_values - baseline_mean) / (baseline_std + 1e-10)
                outliers = np.abs(z_scores) > 2
                
                self.analysis_results[feature] = {
                    'task_mean': np.mean(task_values),
                    'task_std': np.std(task_values),
                    'baseline_mean': baseline_mean,
                    'baseline_std': baseline_std,
                    'z_scores': z_scores,
                    'outliers': outliers,
                    'outlier_percentage': np.sum(outliers) / len(outliers) * 100,
                    'significant_change': abs(np.mean(task_values) - baseline_mean) > 2 * baseline_std
                }
        
        print(f"Task analysis completed for {len(self.analysis_results)} features")
        return self.analysis_results

# --- Main Window ---
class BrainLinkAnalyzerWindow(QMainWindow):
    battery_update = Signal(object, object)
    _active_window: Optional[weakref.ReferenceType] = None
    def __init__(self, user_os, parent=None):
        super().__init__(parent)
        self.user_os = user_os
        self.setWindowTitle(f"MindLink Feature Analyzer - {self.user_os}")
        try:
            self.setWindowIcon(QIcon(resource_path("assets/favicon.ico")))
        except:
            pass
        
        # Settings (reuse for storing HWID substrings)
        self.settings = QSettings("MindLink", "FeatureAnalyzer")
        # Load previously stored allowed HWIDs (comma separated)
        try:
            stored_hwids = self.settings.value("allowed_hwids", "")
            if stored_hwids:
                tokens = [s.strip() for s in str(stored_hwids).split(',') if s.strip()]
                if tokens:
                    # Update global list in-place
                    ALLOWED_HWIDS.clear()
                    ALLOWED_HWIDS.extend(tokens)
        except Exception as e:
            print(f"Failed loading stored HWIDs: {e}")
        
        self.jwt_token = None
        self.brainlink_thread = None
        self.serial_obj = None
        self.feature_engine = FeatureAnalysisEngine()
        self._tasks_complete = False

        self._battery_widget = None
        self._primary_battery_entry = None
        self.battery_status_label = None
        self.battery_progress = None
        self._battery_level: Optional[int] = None
        self._battery_version = None
        self._battery_widgets: List[Dict[str, Any]] = []
        self._pending_battery_update: Optional[tuple] = None
        self._task_overlay = None
        self._active_task_dialog = None
        self._active_task_type = None

        try:
            self.battery_update.connect(self._apply_battery_update)
        except Exception:
            pass

        try:
            BrainLinkAnalyzerWindow._active_window = weakref.ref(self)
        except Exception:
            BrainLinkAnalyzerWindow._active_window = None
        
        self.setMinimumSize(1200, 800)
        self.setup_ui()
        self.setup_timers()
            
    # Initialize windowed task pipeline session holders
        self._sessionA_signal = None
        self._sessionA_events = None
        self._sessionB_signal = None
        self._sessionB_events = None
        self._task_pipeline_results_A = None
        self._task_pipeline_results_B = None

        # Auto-stop timer for baseline calibrations
        self._calibration_timer = QTimer(self)
        self._calibration_timer.setSingleShot(True)
        self._calibration_timer.timeout.connect(self._auto_stop_calibration)
        
        # Attempt device detection
        global SERIAL_PORT
        SERIAL_PORT = detect_brainlink()
        if not SERIAL_PORT and platform.system() == 'Darwin':
            # Offer manual entry for macOS users (Bluetooth / USB descriptor substring)
            if self.prompt_for_device_identifiers():
                SERIAL_PORT = detect_brainlink()
        
        if SERIAL_PORT:
            self.log_message(f"Found MindLink device: {SERIAL_PORT}")
            self.auto_connect_brainlink()
        else:
            self.log_message("ERROR: No MindLink device found!")
            self.log_message("If you're on macOS you can click 'Manual Device Setup' to enter a serial substring or descriptor keyword (e.g. part of HWID, VID:PID, or the legacy 'brainlink' tag).")
            self.log_message("CRITICAL: This application requires a real MindLink device connected.")
            # Disable functionality until device present
            self.setEnabled(False)
            # Re-enable just the manual setup button (added later in UI build)
            if hasattr(self, 'rescan_button'):
                self.rescan_button.setEnabled(True)

    # ...existing code...
    def setup_connection_tab(self):
        """Setup connection and authentication tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Environment selection
        env_group = QGroupBox("Environment")
        env_layout = QHBoxLayout()
        
        self.env_group = QButtonGroup(self)
        self.radio_en = QRadioButton("EN (Production)")
        self.radio_nl = QRadioButton("NL (Production)")
        self.radio_local = QRadioButton("Local (127.0.0.1:5000)")
        self.radio_en.setChecked(True)
        
        self.env_group.addButton(self.radio_en)
        self.env_group.addButton(self.radio_nl)
        self.env_group.addButton(self.radio_local)
        
        env_layout.addWidget(self.radio_en)
        env_layout.addWidget(self.radio_nl)
        env_layout.addWidget(self.radio_local)
        env_group.setLayout(env_layout)
        layout.addWidget(env_group)
        
        # Connection controls
        conn_group = QGroupBox("Connection")
        conn_layout = QHBoxLayout()

        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self.on_connect_clicked)
        conn_layout.addWidget(self.connect_button)
        
        self.disconnect_button = QPushButton("Disconnect")
        self.disconnect_button.clicked.connect(self.on_disconnect_clicked)
        self.disconnect_button.setEnabled(False)
        conn_layout.addWidget(self.disconnect_button)
        
        # Manual device setup button (HWID identifiers)
        self.rescan_button = QPushButton("Manual Device Setup")
        self.rescan_button.setToolTip("Enter HWID / serial / descriptor keywords for MindLink detection")
        self.rescan_button.clicked.connect(self.manual_rescan_devices)
        conn_layout.addWidget(self.rescan_button)
        
        # New: Manual port entry (direct /dev/tty.* or COMx)
        self.manual_port_button = QPushButton("Enter Port")
        self.manual_port_button.setToolTip("Directly specify device path (e.g. /dev/tty.usbserial-XXXX or COM5)")
        self.manual_port_button.clicked.connect(self.manual_enter_port)
        conn_layout.addWidget(self.manual_port_button)
        
        conn_group.setLayout(conn_layout)
        layout.addWidget(conn_group)
        
        # Live EEG plot
        plot_group = QGroupBox("Live EEG Signal")
        plot_layout = QVBoxLayout()
        
        self.plot_widget = pg.PlotWidget(background="#ffffff")
        self.plot_widget.setLabel('left', 'Amplitude (µV)')
        self.plot_widget.setLabel('bottom', 'Sample Index')
        self.plot_widget.setTitle('Raw EEG Signal (upto 10s visual delay) (Real-time)')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.15)
        self.plot_widget.setYRange(-200, 200)
        self.plot_widget.setXRange(0, 256)
        plot_layout.addWidget(self.plot_widget)
        
        # Create plot curve with modern professional colour
        try:
            pen = pg.mkPen(color='#1976d2', width=2, cosmetic=True)
        except Exception:
            pen = pg.mkPen(color='#1976d2', width=2)
        
        # Use plot item directly to avoid autoRangeEnabled issues
        plot_item = self.plot_widget.getPlotItem()
        for axis_name in ('left', 'bottom'):
            axis = plot_item.getAxis(axis_name)
            axis.setPen(pg.mkPen('#bdbdbd'))
            axis.setTextPen(pg.mkPen('#424242'))
        self.live_curve = plot_item.plot([], [], pen=pen, symbol=None)
        
        # Disable auto range to avoid Qt6 compatibility issues
        try:
            plot_item.enableAutoRange('x', False)
            plot_item.enableAutoRange('y', False)
        except Exception:
            pass
        
        plot_group.setLayout(plot_layout)
        layout.addWidget(plot_group)

        # Blink detection controls (runtime diagnostic only)
        blink_group = QGroupBox("Blink Detection (diagnostic)")
        blink_layout = QHBoxLayout()
        self.blink_start_button = QPushButton("Start Blink Monitor")
        self.blink_stop_button = QPushButton("Stop Blink Monitor")
        self.blink_stop_button.setEnabled(False)
        self.blink_status = QLabel("Idle")
        self.blink_status.setStyleSheet(
            "padding: 4px 10px; border-radius: 6px; background-color: #e3f2fd; color: #0d47a1;"
        )
        self.blink_start_button.clicked.connect(self.start_blink_monitor)
        self.blink_stop_button.clicked.connect(self.stop_blink_monitor)
        blink_layout.addWidget(self.blink_start_button)
        blink_layout.addWidget(self.blink_stop_button)
        blink_layout.addWidget(self.blink_status)
        blink_group.setLayout(blink_layout)
        layout.addWidget(blink_group)
        
        # Log area
        log_group = QGroupBox("System Log")
        log_layout = QVBoxLayout()

        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMaximumHeight(140)
        log_layout.addWidget(self.log_area)
        
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)

        # Progression control
        proceed_row = QHBoxLayout()
        proceed_row.addStretch()
        self.proceed_to_analysis_button = QPushButton("Proceed to Tasks")
        self.proceed_to_analysis_button.setEnabled(False)
        self.proceed_to_analysis_button.clicked.connect(self.handle_proceed_to_analysis)
        proceed_row.addWidget(self.proceed_to_analysis_button)
        layout.addLayout(proceed_row)
        
        self.connection_tab_index = self.tabs.addTab(tab, "Connection")

    # ...existing code...
    def manual_enter_port(self):
        """Prompt user for explicit serial port (Windows COMx or macOS /dev/tty.*)."""
        global SERIAL_PORT
        if self.serial_obj and self.serial_obj.is_open:
            QMessageBox.warning(self, "Already Connected", "Disconnect before changing the port.")
            return
        suggested = SERIAL_PORT if SERIAL_PORT else ("COM5" if platform.system() == 'Windows' else "/dev/tty.usbserial-")
        port_text, ok = QInputDialog.getText(self, "Enter Serial Port", "Enter port name/path:", QLineEdit.Normal, suggested)
        if not ok or not port_text.strip():
            return
        port_text = port_text.strip()
        # Basic validation
        if platform.system() == 'Windows':
            if not port_text.upper().startswith('COM'):
                QMessageBox.warning(self, "Invalid Port", "Windows ports must start with COM (e.g. COM5).")
                return
        else:
            if not port_text.startswith('/dev/'):
                QMessageBox.warning(self, "Invalid Path", "macOS/Linux ports usually start with /dev/ (e.g. /dev/tty.usbserial-XXXX).")
                return
        SERIAL_PORT = port_text
        self.log_message(f"User specified port: {SERIAL_PORT}")
        # Attempt connection without disabling UI if fails
        try:
            self.auto_connect_brainlink()
        except Exception as e:
            self.log_message(f"Manual connect failed: {e}")

    # ...existing code...
    def auto_connect_brainlink(self):
        """Auto-connect to MindLink device for console output"""
        global SERIAL_PORT, stop_thread_flag
        
        try:
            self.log_message("Auto-connecting to MindLink device...")
            
            # Link feature engine to onRaw callback
            onRaw.feature_engine = self.feature_engine
            
            # Create serial object
            self.serial_obj = CushySerial(SERIAL_PORT, SERIAL_BAUD)
            
            # Reset stop flag
            stop_thread_flag = False
            
            # Start MindLink thread
            self.brainlink_thread = threading.Thread(target=run_brainlink, args=(self.serial_obj,))
            self.brainlink_thread.daemon = True
            self.brainlink_thread.start()
            
            # Enable calibration buttons for immediate testing
            self.eyes_closed_button.setEnabled(True)
            self.eyes_open_button.setEnabled(True)
            self.task_button.setEnabled(True)
            self._set_feature_status("Connected", "ready")
            self._reset_workflow_progress()
            if hasattr(self, 'proceed_to_analysis_button'):
                self.proceed_to_analysis_button.setEnabled(True)
            
            # Initialize task preview with the first task
            if self.task_combo.count() > 0:
                self.update_task_preview(self.task_combo.currentText())
            
            self.log_message("✓ MindLink auto-connected! Check console for processed values.")
            print("\n" + "="*60)
            print("MINDLINK ANALYZER STARTED")
            print("Real-time EEG analysis will appear in console every 50 samples")
            print("="*60)
            
        except Exception as e:
            self.log_message(f"Auto-connect failed: {e}")
            print(f"Auto-connect error: {e}")
            # Enable manual connection
            self.connect_button.setEnabled(True)
    
    def setup_ui(self):
        """Setup the user interface"""
        self.setStyleSheet("""
            QMainWindow { background:#f5f7fa; }
            QLabel { font-size:13px; color:#2c3e50; }
            QPushButton {
                background-color:#1976d2;
                color:#ffffff;
                border-radius:6px;
                padding:8px 18px;
                font-size:13px;
                border:0;
            }
            QPushButton:hover { background-color:#1e88e5; }
            QPushButton:pressed { background-color:#1565c0; }
            QPushButton:disabled { background-color:#cfd8dc; color:#607d8b; }
            QRadioButton { font-size:13px; color:#37474f; }
            QGroupBox {
                margin-top:12px;
                border:1px solid #dfe4ea;
                border-radius:10px;
                padding:12px 14px 14px 14px;
                background:#ffffff;
            }
            QLineEdit, QComboBox {
                font-size:13px;
                padding:6px 8px;
                background:#ffffff;
                color:#2c3e50;
                border:1px solid #cfd8dc;
                border-radius:6px;
            }
            QTextEdit {
                font-size:13px;
                background:#ffffff;
                color:#2c3e50;
                border:1px solid #cfd8dc;
                border-radius:8px;
                padding:8px;
            }
            QTabWidget::pane {
                border:1px solid #dfe4ea;
                border-radius:10px;
                background:#ffffff;
                margin-top:6px;
            }
            QTabBar::tab {
                background:#eef2f5;
                color:#546e7a;
                padding:10px 22px;
                border-top-left-radius:10px;
                border-top-right-radius:10px;
                margin-right:4px;
            }
            QTabBar::tab:selected {
                background:#ffffff;
                color:#1976d2;
                border:1px solid #dfe4ea;
                border-bottom-color:#ffffff;
            }
            QTabBar::tab:hover { background:#ffffff; color:#1e88e5; }
        """)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Header row with battery indicator
        header_container = QWidget()
        header_container.setObjectName("HeaderRow")
        header_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        header_layout = QHBoxLayout(header_container)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(12)

        header = QLabel("MindLink Feature Analyzer")
        header.setAlignment(Qt.AlignLeft)
        header.setStyleSheet("font-size: 20px; font-weight: bold;")
        header_layout.addWidget(header)

        header_layout.addStretch()

        try:
            battery_widget = self._build_battery_indicator()
            header_layout.addWidget(battery_widget, 0, Qt.AlignRight)
        except Exception:
            battery_widget = None

        main_layout.addWidget(header_container)
        
        # Tab widget
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        main_layout.addWidget(self.tabs)

        # Setup primary sections
        self.setup_connection_tab()
        self.setup_analysis_tab()
        self.setup_tasks_tab()  # Multi-task pipeline

        self.tabs.setCurrentIndex(self.connection_tab_index)

        # Status bar
        self.status_label = QLabel("Ready")
        main_layout.addWidget(self.status_label)
        
    def setup_connection_tab(self):
        """Setup connection and authentication tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Environment selection
        env_group = QGroupBox("Environment")
        env_layout = QHBoxLayout()
        
        self.env_group = QButtonGroup(self)
        self.radio_en = QRadioButton("EN (Production)")
        self.radio_nl = QRadioButton("NL (Production)")
        self.radio_local = QRadioButton("Local (127.0.0.1:5000)")
        self.radio_en.setChecked(True)
        
        self.env_group.addButton(self.radio_en)
        self.env_group.addButton(self.radio_nl)
        self.env_group.addButton(self.radio_local)
        
        env_layout.addWidget(self.radio_en)
        env_layout.addWidget(self.radio_nl)
        env_layout.addWidget(self.radio_local)
        env_group.setLayout(env_layout)
        layout.addWidget(env_group)
        
        # Connection controls
        conn_group = QGroupBox("Connection")
        conn_layout = QHBoxLayout()

        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self.on_connect_clicked)
        conn_layout.addWidget(self.connect_button)
        
        self.disconnect_button = QPushButton("Disconnect")
        self.disconnect_button.clicked.connect(self.on_disconnect_clicked)
        self.disconnect_button.setEnabled(False)
        conn_layout.addWidget(self.disconnect_button)
        
        # Manual device setup button (HWID identifiers)
        self.rescan_button = QPushButton("Manual Device Setup")
        self.rescan_button.setToolTip("Enter HWID / serial / descriptor keywords for MindLink detection")
        self.rescan_button.clicked.connect(self.manual_rescan_devices)
        conn_layout.addWidget(self.rescan_button)
        
        # New: Manual port entry (direct /dev/tty.* or COMx)
        self.manual_port_button = QPushButton("Enter Port")
        self.manual_port_button.setToolTip("Directly specify device path (e.g. /dev/tty.usbserial-XXXX or COM5)")
        self.manual_port_button.clicked.connect(self.manual_enter_port)
        conn_layout.addWidget(self.manual_port_button)
        
        conn_group.setLayout(conn_layout)
        layout.addWidget(conn_group)
        
        # Live EEG plot
        plot_group = QGroupBox("Live EEG Signal")
        plot_layout = QVBoxLayout()
        
        self.plot_widget = pg.PlotWidget(background="#ffffff")
        self.plot_widget.setLabel('left', 'Amplitude (µV)')
        self.plot_widget.setLabel('bottom', 'Sample Index')
        self.plot_widget.setTitle('Raw EEG Signal (upto 10s visual delay) (Real-time)')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.15)
        self.plot_widget.setYRange(-200, 200)
        self.plot_widget.setXRange(0, 256)
        plot_layout.addWidget(self.plot_widget)
        
        # Create plot curve with modern professional colour
        try:
            pen = pg.mkPen(color='#1976d2', width=2, cosmetic=True)
        except Exception:
            pen = pg.mkPen(color='#1976d2', width=2)
        
        # Use plot item directly to avoid autoRangeEnabled issues
        plot_item = self.plot_widget.getPlotItem()
        for axis_name in ('left', 'bottom'):
            axis = plot_item.getAxis(axis_name)
            axis.setPen(pg.mkPen('#bdbdbd'))
            axis.setTextPen(pg.mkPen('#424242'))
        self.live_curve = plot_item.plot([], [], pen=pen, symbol=None)
        
        # Disable auto range to avoid Qt6 compatibility issues
        try:
            plot_item.enableAutoRange('x', False)
            plot_item.enableAutoRange('y', False)
        except Exception:
            pass
        
        plot_group.setLayout(plot_layout)
        layout.addWidget(plot_group)

        # Blink detection controls (runtime diagnostic only)
        blink_group = QGroupBox("Blink Detection (diagnostic)")
        blink_layout = QHBoxLayout()
        self.blink_start_button = QPushButton("Start Blink Monitor")
        self.blink_stop_button = QPushButton("Stop Blink Monitor")
        self.blink_stop_button.setEnabled(False)
        self.blink_status = QLabel("Idle")
        self.blink_status.setStyleSheet(
            "padding: 4px 10px; border-radius: 6px; background-color: #e3f2fd; color: #0d47a1;"
        )
        self.blink_start_button.clicked.connect(self.start_blink_monitor)
        self.blink_stop_button.clicked.connect(self.stop_blink_monitor)
        blink_layout.addWidget(self.blink_start_button)
        blink_layout.addWidget(self.blink_stop_button)
        blink_layout.addWidget(self.blink_status)
        blink_group.setLayout(blink_layout)
        layout.addWidget(blink_group)
        
        # Log area
        log_group = QGroupBox("System Log")
        log_layout = QVBoxLayout()
        
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMaximumHeight(140)
        log_layout.addWidget(self.log_area)
        
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)
        
        self.tabs.addTab(tab, "Connection")

    # ...existing code...
    def manual_enter_port(self):
        """Prompt user for explicit serial port (Windows COMx or macOS /dev/tty.*)."""
        global SERIAL_PORT
        if self.serial_obj and self.serial_obj.is_open:
            QMessageBox.warning(self, "Already Connected", "Disconnect before changing the port.")
            return
        suggested = SERIAL_PORT if SERIAL_PORT else ("COM5" if platform.system() == 'Windows' else "/dev/tty.usbserial-")
        port_text, ok = QInputDialog.getText(self, "Enter Serial Port", "Enter port name/path:", QLineEdit.Normal, suggested)
        if not ok or not port_text.strip():
            return
        port_text = port_text.strip()
        # Basic validation
        if platform.system() == 'Windows':
            if not port_text.upper().startswith('COM'):
                QMessageBox.warning(self, "Invalid Port", "Windows ports must start with COM (e.g. COM5).")
                return
        else:
            if not port_text.startswith('/dev/'):
                QMessageBox.warning(self, "Invalid Path", "macOS/Linux ports usually start with /dev/ (e.g. /dev/tty.usbserial-XXXX).")
                return
        SERIAL_PORT = port_text
        self.log_message(f"User specified port: {SERIAL_PORT}")
        # Attempt connection without disabling UI if fails
        try:
            self.auto_connect_brainlink()
        except Exception as e:
            self.log_message(f"Manual connect failed: {e}")

    # ...existing code...
    def auto_connect_brainlink(self):
        """Auto-connect to MindLink device for console output"""
        global SERIAL_PORT, stop_thread_flag
        
        try:
            self.log_message("Auto-connecting to MindLink device...")
            
            # Link feature engine to onRaw callback
            onRaw.feature_engine = self.feature_engine
            
            # Create serial object
            self.serial_obj = CushySerial(SERIAL_PORT, SERIAL_BAUD)
            
            # Reset stop flag
            stop_thread_flag = False
            
            # Start MindLink thread
            self.brainlink_thread = threading.Thread(target=run_brainlink, args=(self.serial_obj,))
            self.brainlink_thread.daemon = True
            self.brainlink_thread.start()
            
            # Enable calibration buttons for immediate testing
            self.eyes_closed_button.setEnabled(True)
            self.eyes_open_button.setEnabled(True)
            self.task_button.setEnabled(True)
            self._set_feature_status("Connected", "ready")
            
            # Initialize task preview with the first task
            if self.task_combo.count() > 0:
                self.update_task_preview(self.task_combo.currentText())
            
            self.log_message("✓ MindLink auto-connected! Check console for processed values.")
            print("\n" + "="*60)
            print("MINDLINK ANALYZER STARTED")
            print("Real-time EEG analysis will appear in console every 50 samples")
            print("="*60)
            
        except Exception as e:
            self.log_message(f"Auto-connect failed: {e}")
            print(f"Auto-connect error: {e}")
            # Enable manual connection
            self.connect_button.setEnabled(True)
    
    def setup_ui(self):
        """Setup the user interface"""
        self.setStyleSheet("""
            QMainWindow { background:#f5f7fb; }
            QLabel { font-size:13px; color:#1f2933; }
            QPushButton {
                background-color:#2563eb;
                color:#ffffff;
                border-radius:8px;
                padding:10px 18px;
                font-size:13px;
                font-weight:600;
            }
            QPushButton:disabled {
                background-color:#d1d5db;
                color:#6b7280;
            }
            QRadioButton { font-size:13px; color:#374151; }
            QGroupBox {
                margin-top:12px;
                border:1px solid #e5e7eb;
                border-radius:12px;
                padding:16px;
                background:#ffffff;
            }
            QLineEdit, QComboBox {
                font-size:13px;
                padding:8px 10px;
                background:#ffffff;
                color:#111827;
                border:1px solid #d1d5db;
                border-radius:8px;
            }
            QTextEdit {
                font-size:13px;
                background:#ffffff;
                color:#111827;
                border:1px solid #d1d5db;
                border-radius:12px;
                padding:12px;
            }
            QTabWidget::pane {
                border:1px solid #e5e7eb;
                border-radius:12px;
                background:#ffffff;
                margin-top:8px;
            }
            QTabBar::tab {
                background:#eef2ff;
                color:#3b82f6;
                padding:10px 24px;
                border-top-left-radius:10px;
                border-top-right-radius:10px;
                margin-right:6px;
            }
            QTabBar::tab:selected {
                background:#ffffff;
                color:#1d4ed8;
                border:1px solid #dbe2ff;
                border-bottom-color:#ffffff;
            }
            QTabBar::tab:hover {
                background:#ffffff;
                color:#2563eb;
            }
        """)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(18)

        header_container = QWidget()
        header_container.setObjectName("HeaderRow")
        header_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        header_layout = QHBoxLayout(header_container)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(12)

        header = QLabel("MindLink Feature Analyzer")
        header.setAlignment(Qt.AlignLeft)
        header.setStyleSheet("font-size:22px; font-weight:700; letter-spacing:0.5px;")
        header_layout.addWidget(header)

        header_layout.addStretch()

        try:
            battery_widget = self._build_battery_indicator()
            header_layout.addWidget(battery_widget, 0, Qt.AlignRight)
        except Exception:
            battery_widget = None

        main_layout.addWidget(header_container)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(False)
        main_layout.addWidget(self.tabs)

        self.setup_connection_tab()
        self.setup_analysis_tab()
        self.setup_tasks_tab()

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color:#475569; font-size:12px;")
        main_layout.addWidget(self.status_label)
        
    def setup_connection_tab(self):
        """Setup connection and authentication tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Environment selection
        env_group = QGroupBox("Environment")
        env_layout = QHBoxLayout()
        
        self.env_group = QButtonGroup(self)
        self.radio_en = QRadioButton("EN (Production)")
        self.radio_nl = QRadioButton("NL (Production)")
        self.radio_local = QRadioButton("Local (127.0.0.1:5000)")
        self.radio_en.setChecked(True)
        
        self.env_group.addButton(self.radio_en)
        self.env_group.addButton(self.radio_nl)
        self.env_group.addButton(self.radio_local)
        
        env_layout.addWidget(self.radio_en)
        env_layout.addWidget(self.radio_nl)
        env_layout.addWidget(self.radio_local)
        env_group.setLayout(env_layout)
        layout.addWidget(env_group)
        
        # Connection controls
        conn_group = QGroupBox("Connection")
        conn_layout = QHBoxLayout()

        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self.on_connect_clicked)
        conn_layout.addWidget(self.connect_button)
        
        self.disconnect_button = QPushButton("Disconnect")
        self.disconnect_button.clicked.connect(self.on_disconnect_clicked)
        self.disconnect_button.setEnabled(False)
        conn_layout.addWidget(self.disconnect_button)
        
        # Manual device setup button (HWID identifiers)
        self.rescan_button = QPushButton("Manual Device Setup")
        self.rescan_button.setToolTip("Enter HWID / serial / descriptor keywords for MindLink detection")
        self.rescan_button.clicked.connect(self.manual_rescan_devices)
        conn_layout.addWidget(self.rescan_button)
        
        # New: Manual port entry (direct /dev/tty.* or COMx)
        self.manual_port_button = QPushButton("Enter Port")
        self.manual_port_button.setToolTip("Directly specify device path (e.g. /dev/tty.usbserial-XXXX or COM5)")
        self.manual_port_button.clicked.connect(self.manual_enter_port)
        conn_layout.addWidget(self.manual_port_button)
        
        conn_group.setLayout(conn_layout)
        layout.addWidget(conn_group)
        
        # Live EEG plot
        plot_group = QGroupBox("Live EEG Signal")
        plot_layout = QVBoxLayout()
        
        self.plot_widget = pg.PlotWidget(background="#ffffff")
        self.plot_widget.setLabel('left', 'Amplitude (µV)')
        self.plot_widget.setLabel('bottom', 'Sample Index')
        self.plot_widget.setTitle('Raw EEG Signal (upto 10s visual delay) (Real-time)')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.15)
        self.plot_widget.setYRange(-200, 200)
        self.plot_widget.setXRange(0, 256)
        plot_layout.addWidget(self.plot_widget)
        
        # Create plot curve with modern professional colour
        try:
            pen = pg.mkPen(color='#1976d2', width=2, cosmetic=True)
        except Exception:
            pen = pg.mkPen(color='#1976d2', width=2)
        
        # Use plot item directly to avoid autoRangeEnabled issues
        plot_item = self.plot_widget.getPlotItem()
        for axis_name in ('left', 'bottom'):
            axis = plot_item.getAxis(axis_name)
            axis.setPen(pg.mkPen('#bdbdbd'))
            axis.setTextPen(pg.mkPen('#424242'))
        self.live_curve = plot_item.plot([], [], pen=pen, symbol=None)
        
        # Disable auto range to avoid Qt6 compatibility issues
        try:
            plot_item.enableAutoRange('x', False)
            plot_item.enableAutoRange('y', False)
        except Exception:
            pass
        
        plot_group.setLayout(plot_layout)
        layout.addWidget(plot_group)

        # Blink detection controls (runtime diagnostic only)
        blink_group = QGroupBox("Blink Detection (diagnostic)")
        blink_layout = QHBoxLayout()
        self.blink_start_button = QPushButton("Start Blink Monitor")
        self.blink_stop_button = QPushButton("Stop Blink Monitor")
        self.blink_stop_button.setEnabled(False)
        self.blink_status = QLabel("Idle")
        self.blink_status.setStyleSheet(
            "padding: 4px 10px; border-radius: 6px; background-color: #e3f2fd; color: #0d47a1;"
        )
        self.blink_start_button.clicked.connect(self.start_blink_monitor)
        self.blink_stop_button.clicked.connect(self.stop_blink_monitor)
        blink_layout.addWidget(self.blink_start_button)
        blink_layout.addWidget(self.blink_stop_button)
        blink_layout.addWidget(self.blink_status)
        blink_group.setLayout(blink_layout)
        layout.addWidget(blink_group)
        
        # Log area
        log_group = QGroupBox("System Log")
        log_layout = QVBoxLayout()
        
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMaximumHeight(140)
        log_layout.addWidget(self.log_area)
        
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)
        
        self.tabs.addTab(tab, "Connection")

    # ...existing code...
    def manual_enter_port(self):
        """Prompt user for explicit serial port (Windows COMx or macOS /dev/tty.*)."""
        global SERIAL_PORT
        if self.serial_obj and self.serial_obj.is_open:
            QMessageBox.warning(self, "Already Connected", "Disconnect before changing the port.")
            return
        suggested = SERIAL_PORT if SERIAL_PORT else ("COM5" if platform.system() == 'Windows' else "/dev/tty.usbserial-")
        port_text, ok = QInputDialog.getText(self, "Enter Serial Port", "Enter port name/path:", QLineEdit.Normal, suggested)
        if not ok or not port_text.strip():
            return
        port_text = port_text.strip()
        # Basic validation
        if platform.system() == 'Windows':
            if not port_text.upper().startswith('COM'):
                QMessageBox.warning(self, "Invalid Port", "Windows ports must start with COM (e.g. COM5).")
                return
        else:
            if not port_text.startswith('/dev/'):
                QMessageBox.warning(self, "Invalid Path", "macOS/Linux ports usually start with /dev/ (e.g. /dev/tty.usbserial-XXXX).")
                return
        SERIAL_PORT = port_text
        self.log_message(f"User specified port: {SERIAL_PORT}")
        # Attempt connection without disabling UI if fails
        try:
            self.auto_connect_brainlink()
        except Exception as e:
            self.log_message(f"Manual connect failed: {e}")

    # ...existing code...
    def auto_connect_brainlink(self):
        """Auto-connect to MindLink device for console output"""
        global SERIAL_PORT, stop_thread_flag
        
        try:
            self.log_message("Auto-connecting to MindLink device...")
            
            # Link feature engine to onRaw callback
            onRaw.feature_engine = self.feature_engine
            
            # Create serial object
            self.serial_obj = CushySerial(SERIAL_PORT, SERIAL_BAUD)
            
            # Reset stop flag
            stop_thread_flag = False
            
            # Start MindLink thread
            self.brainlink_thread = threading.Thread(target=run_brainlink, args=(self.serial_obj,))
            self.brainlink_thread.daemon = True
            self.brainlink_thread.start()
            
            # Enable calibration buttons for immediate testing
            self.eyes_closed_button.setEnabled(True)
            self.eyes_open_button.setEnabled(True)
            self.task_button.setEnabled(True)
            self._set_feature_status("Connected", "ready")
            
            # Initialize task preview with the first task
            if self.task_combo.count() > 0:
                self.update_task_preview(self.task_combo.currentText())
            
            self.log_message("✓ MindLink auto-connected! Check console for processed values.")
            print("\n" + "="*60)
            print("MINDLINK ANALYZER STARTED")
            print("Real-time EEG analysis will appear in console every 50 samples")
            print("="*60)
            
        except Exception as e:
            self.log_message(f"Auto-connect failed: {e}")
            print(f"Auto-connect error: {e}")
            # Enable manual connection
            self.connect_button.setEnabled(True)
    
    def setup_ui(self):
        """Setup the user interface"""
        self.setStyleSheet("""
            QWidget {
                color: #1f2937;
                background: #f9fafb;
                font-size: 12px;
            }
            QMainWindow {
                background: #f3f4f6;
            }
            QLabel#AppTitle {
                font-size: 22px;
                font-weight: 600;
                color: #0f172a;
            }
            QLabel {
                font-size: 12px;
            }
            QPushButton {
                background-color: #1d4ed8;
                color: #ffffff;
                border: none;
                border-radius: 8px;
                padding: 10px 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #1e40af;
            }
            QPushButton:pressed {
                background-color: #1e3a8a;
            }
            QPushButton:disabled {
                background-color: #cbd5f5;
                color: #64748b;
            }
            QRadioButton {
                font-size: 12px;
            }
            QGroupBox {
                border: 1px solid #e5e7eb;
                border-radius: 12px;
                margin-top: 12px;
                padding: 14px;
                background: #ffffff;
            }
            QLineEdit, QTextEdit {
                border: 1px solid #d1d5db;
                border-radius: 8px;
                padding: 8px;
                background: #ffffff;
            }
            QComboBox {
                border: 1px solid #d1d5db;
                border-radius: 8px;
                padding: 8px 36px 8px 10px;
                background: #ffffff;
                color: #1f2937;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 32px;
                border-left: 1px solid #dbe0e6;
                background-color: #eef2f8;
                border-top-right-radius: 8px;
                border-bottom-right-radius: 8px;
            }
            QComboBox::down-arrow {
                width: 0;
                height: 0;
                margin-right: 10px;
                border-left: 6px solid transparent;
                border-right: 6px solid transparent;
                border-top: 8px solid #1d4ed8;
            }
            QComboBox::down-arrow:on {
                border-top-color: #1e3a8a;
            }
            QTextEdit {
                line-height: 1.4;
            }
            QTabWidget::pane {
                border: none;
            }
            QTabBar::tab {
                padding: 10px 16px;
                border: none;
                margin-right: 6px;
                border-radius: 10px 10px 0 0;
                background: #e5e7eb;
                color: #334155;
                font-weight: 600;
            }
            QTabBar::tab:selected {
                background: #ffffff;
                color: #111827;
            }
            QScrollBar:vertical {
                width: 10px;
                background: #e5e7eb;
                margin: 0px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background: #94a3b8;
                min-height: 30px;
                border-radius: 5px;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0;
            }
        """)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(20)

        header = QLabel("MindLink Feature Analyzer")
        header.setObjectName("AppTitle")
        header.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(header)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setTabBarAutoHide(False)
        main_layout.addWidget(self.tabs)

        self.setup_connection_tab()
        self.setup_analysis_tab()
        self.setup_tasks_tab()

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color:#475569; font-weight:500;")
        main_layout.addWidget(self.status_label)
        
    def setup_connection_tab(self):
        """Setup connection and authentication tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Environment selection
        env_group = QGroupBox("Environment")
        env_layout = QHBoxLayout()
        
        self.env_group = QButtonGroup(self)
        self.radio_en = QRadioButton("EN (Production)")
        self.radio_nl = QRadioButton("NL (Production)")
        self.radio_local = QRadioButton("Local (127.0.0.1:5000)")
        self.radio_en.setChecked(True)
        
        self.env_group.addButton(self.radio_en)
        self.env_group.addButton(self.radio_nl)
        self.env_group.addButton(self.radio_local)
        
        env_layout.addWidget(self.radio_en)
        env_layout.addWidget(self.radio_nl)
        env_layout.addWidget(self.radio_local)
        env_group.setLayout(env_layout)
        layout.addWidget(env_group)
        
        # Connection controls
        conn_group = QGroupBox("Connection")
        conn_layout = QHBoxLayout()

        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self.on_connect_clicked)
        conn_layout.addWidget(self.connect_button)
        
        self.disconnect_button = QPushButton("Disconnect")
        self.disconnect_button.clicked.connect(self.on_disconnect_clicked)
        self.disconnect_button.setEnabled(False)
        conn_layout.addWidget(self.disconnect_button)
        
        # Manual device setup button (HWID identifiers)
        self.rescan_button = QPushButton("Manual Device Setup")
        self.rescan_button.setToolTip("Enter HWID / serial / descriptor keywords for MindLink detection")
        self.rescan_button.clicked.connect(self.manual_rescan_devices)
        conn_layout.addWidget(self.rescan_button)
        
        # New: Manual port entry (direct /dev/tty.* or COMx)
        self.manual_port_button = QPushButton("Enter Port")
        self.manual_port_button.setToolTip("Directly specify device path (e.g. /dev/tty.usbserial-XXXX or COM5)")
        self.manual_port_button.clicked.connect(self.manual_enter_port)
        conn_layout.addWidget(self.manual_port_button)
        
        conn_group.setLayout(conn_layout)
        layout.addWidget(conn_group)
        
        # Live EEG plot
        plot_group = QGroupBox("Live EEG Signal")
        plot_layout = QVBoxLayout()
        
        self.plot_widget = pg.PlotWidget(background="#ffffff")
        self.plot_widget.setLabel('left', 'Amplitude (µV)')
        self.plot_widget.setLabel('bottom', 'Sample Index')
        self.plot_widget.setTitle('Raw EEG Signal (upto 10s visual delay) (Real-time)')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.15)
        self.plot_widget.setYRange(-200, 200)
        self.plot_widget.setXRange(0, 256)
        plot_layout.addWidget(self.plot_widget)
        
        # Create plot curve with modern professional colour
        try:
            pen = pg.mkPen(color='#1976d2', width=2, cosmetic=True)
        except Exception:
            pen = pg.mkPen(color='#1976d2', width=2)
        
        # Use plot item directly to avoid autoRangeEnabled issues
        plot_item = self.plot_widget.getPlotItem()
        for axis_name in ('left', 'bottom'):
            axis = plot_item.getAxis(axis_name)
            axis.setPen(pg.mkPen('#bdbdbd'))
            axis.setTextPen(pg.mkPen('#424242'))
        self.live_curve = plot_item.plot([], [], pen=pen, symbol=None)
        
        # Disable auto range to avoid Qt6 compatibility issues
        try:
            plot_item.enableAutoRange('x', False)
            plot_item.enableAutoRange('y', False)
        except Exception:
            pass
        
        plot_group.setLayout(plot_layout)
        layout.addWidget(plot_group)

        # Blink detection controls (runtime diagnostic only)
        blink_group = QGroupBox("Blink Detection (diagnostic)")
        blink_layout = QHBoxLayout()
        self.blink_start_button = QPushButton("Start Blink Monitor")
        self.blink_stop_button = QPushButton("Stop Blink Monitor")
        self.blink_stop_button.setEnabled(False)
        self.blink_status = QLabel("Idle")
        self.blink_status.setStyleSheet(
            "padding: 4px 10px; border-radius: 6px; background-color: #e3f2fd; color: #0d47a1;"
        )
        self.blink_start_button.clicked.connect(self.start_blink_monitor)
        self.blink_stop_button.clicked.connect(self.stop_blink_monitor)
        blink_layout.addWidget(self.blink_start_button)
        blink_layout.addWidget(self.blink_stop_button)
        blink_layout.addWidget(self.blink_status)
        blink_group.setLayout(blink_layout)
        layout.addWidget(blink_group)
        
        # Log area
        log_group = QGroupBox("System Log")
        log_layout = QVBoxLayout()
        
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMaximumHeight(140)
        log_layout.addWidget(self.log_area)
        
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)
        
        self.tabs.addTab(tab, "Connection")

    # ...existing code...
    def manual_enter_port(self):
        """Prompt user for explicit serial port (Windows COMx or macOS /dev/tty.*)."""
        global SERIAL_PORT
        if self.serial_obj and self.serial_obj.is_open:
            QMessageBox.warning(self, "Already Connected", "Disconnect before changing the port.")
            return
        suggested = SERIAL_PORT if SERIAL_PORT else ("COM5" if platform.system() == 'Windows' else "/dev/tty.usbserial-")
        port_text, ok = QInputDialog.getText(self, "Enter Serial Port", "Enter port name/path:", QLineEdit.Normal, suggested)
        if not ok or not port_text.strip():
            return
        port_text = port_text.strip()
        # Basic validation
        if platform.system() == 'Windows':
            if not port_text.upper().startswith('COM'):
                QMessageBox.warning(self, "Invalid Port", "Windows ports must start with COM (e.g. COM5).")
                return
        else:
            if not port_text.startswith('/dev/'):
                QMessageBox.warning(self, "Invalid Path", "macOS/Linux ports usually start with /dev/ (e.g. /dev/tty.usbserial-XXXX).")
                return
        SERIAL_PORT = port_text
        self.log_message(f"User specified port: {SERIAL_PORT}")
        # Attempt connection without disabling UI if fails
        try:
            self.auto_connect_brainlink()
        except Exception as e:
            self.log_message(f"Manual connect failed: {e}")

    # ...existing code...
    def auto_connect_brainlink(self):
        """Auto-connect to MindLink device for console output"""
        global SERIAL_PORT, stop_thread_flag
        
        try:
            self.log_message("Auto-connecting to MindLink device...")
            
            # Link feature engine to onRaw callback
            onRaw.feature_engine = self.feature_engine
            
            # Create serial object
            self.serial_obj = CushySerial(SERIAL_PORT, SERIAL_BAUD)
            
            # Reset stop flag
            stop_thread_flag = False
            
            # Start MindLink thread
            self.brainlink_thread = threading.Thread(target=run_brainlink, args=(self.serial_obj,))
            self.brainlink_thread.daemon = True
            self.brainlink_thread.start()
            
            # Enable calibration controls for immediate use
            self.eyes_closed_button.setEnabled(True)
            self.eyes_open_button.setEnabled(True)
            self.task_button.setEnabled(True)
            self._set_feature_status("Connected", "ready")

            if self.task_combo.count() > 0:
                self.update_task_preview(self.task_combo.currentText())

            self.log_message("✓ MindLink auto-connected! Check console for processed values.")
            print("\n" + "="*60)
            print("MINDLINK ANALYZER STARTED")
            print("Real-time EEG analysis will appear in console every 50 samples")
            print("="*60)
            
        except Exception as e:
            self.log_message(f"Auto-connect failed: {e}")
            print(f"Auto-connect error: {e}")
            # Enable manual connection
            self.connect_button.setEnabled(True)
    
    def setup_ui(self):
        """Setup the user interface"""
        self.setStyleSheet("""
            QWidget {
                color: #1f2937;
                background: #f9fafb;
                font-size: 12px;
            }
            QMainWindow {
                background: #f3f4f6;
            }
            QLabel#AppTitle {
                font-size: 22px;
                font-weight: 600;
                color: #0f172a;
            }
            QLabel {
                font-size: 12px;
            }
            QPushButton {
                background-color: #1d4ed8;
                color: #ffffff;
                border: none;
                border-radius: 8px;
                padding: 10px 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #1e40af;
            }
            QPushButton:pressed {
                background-color: #1e3a8a;
            }
            QPushButton:disabled {
                background-color: #cbd5f5;
                color: #64748b;
            }
            QRadioButton {
                font-size: 12px;
            }
            QGroupBox {
                border: 1px solid #e5e7eb;
                border-radius: 12px;
                margin-top: 12px;
                padding: 14px;
                background: #ffffff;
            }
            QLineEdit, QComboBox, QTextEdit {
                border: 1px solid #d1d5db;
                border-radius: 8px;
                padding: 8px;
                background: #ffffff;
            }
            QTextEdit {
                line-height: 1.4;
            }
            QTabWidget::pane {
                border: none;
            }
            QTabBar::tab {
                padding: 10px 16px;
                border: none;
                margin-right: 6px;
                border-radius: 10px 10px 0 0;
                background: #e5e7eb;
                color: #334155;
                font-weight: 600;
            }
            QTabBar::tab:selected {
                background: #ffffff;
                color: #111827;
            }
            QScrollBar:vertical {
                width: 10px;
                background: #e5e7eb;
                margin: 0px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background: #94a3b8;
                min-height: 30px;
                border-radius: 5px;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0;
            }
        """)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(20)
        
        header = QLabel("MindLink Feature Analyzer")
        header.setObjectName("AppTitle")
        header.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(header)
        
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setTabBarAutoHide(False)
        main_layout.addWidget(self.tabs)
        
        self.setup_connection_tab()
        self.setup_analysis_tab()
        self.setup_tasks_tab()
        
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color:#475569; font-weight:500;")
        main_layout.addWidget(self.status_label)
        
    def setup_connection_tab(self):
        """Setup connection and authentication tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Environment selection
        env_group = QGroupBox("Environment")
        env_layout = QHBoxLayout()
        
        self.env_group = QButtonGroup(self)
        self.radio_en = QRadioButton("EN (Production)")
        self.radio_nl = QRadioButton("NL (Production)")
        self.radio_local = QRadioButton("Local (127.0.0.1:5000)")
        self.radio_en.setChecked(True)
        
        self.env_group.addButton(self.radio_en)
        self.env_group.addButton(self.radio_nl)
        self.env_group.addButton(self.radio_local)
        
        env_layout.addWidget(self.radio_en)
        env_layout.addWidget(self.radio_nl)
        env_layout.addWidget(self.radio_local)
        env_group.setLayout(env_layout)
        layout.addWidget(env_group)
        
        # Connection controls
        conn_group = QGroupBox("Connection")
        conn_layout = QHBoxLayout()
        
        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self.on_connect_clicked)
        conn_layout.addWidget(self.connect_button)
        
        self.disconnect_button = QPushButton("Disconnect")
        self.disconnect_button.clicked.connect(self.on_disconnect_clicked)
        self.disconnect_button.setEnabled(False)
        conn_layout.addWidget(self.disconnect_button)
        
        # Manual device setup button (HWID identifiers)
        self.rescan_button = QPushButton("Manual Device Setup")
        self.rescan_button.setToolTip("Enter HWID / serial / descriptor keywords for MindLink detection")
        self.rescan_button.clicked.connect(self.manual_rescan_devices)
        conn_layout.addWidget(self.rescan_button)
        
        # New: Manual port entry (direct /dev/tty.* or COMx)
        self.manual_port_button = QPushButton("Enter Port")
        self.manual_port_button.setToolTip("Directly specify device path (e.g. /dev/tty.usbserial-XXXX or COM5)")
        self.manual_port_button.clicked.connect(self.manual_enter_port)
        conn_layout.addWidget(self.manual_port_button)
        
        conn_group.setLayout(conn_layout)
        layout.addWidget(conn_group)
        
        # Live EEG plot
        plot_group = QGroupBox("Live EEG Signal")
        plot_layout = QVBoxLayout()
        
        self.plot_widget = pg.PlotWidget(background="#ffffff")
        self.plot_widget.setLabel('left', 'Amplitude (µV)')
        self.plot_widget.setLabel('bottom', 'Sample Index')
        self.plot_widget.setTitle('Raw EEG Signal (upto 10s visual delay) (Real-time)')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.15)
        self.plot_widget.setYRange(-200, 200)
        self.plot_widget.setXRange(0, 256)
        plot_layout.addWidget(self.plot_widget)
        
        # Create plot curve with modern professional colour
        try:
            pen = pg.mkPen(color='#1976d2', width=2, cosmetic=True)
        except Exception:
            pen = pg.mkPen(color='#1976d2', width=2)

        # Use plot item directly to avoid autoRangeEnabled issues
        plot_item = self.plot_widget.getPlotItem()
        for axis_name in ('left', 'bottom'):
            axis = plot_item.getAxis(axis_name)
            axis.setPen(pg.mkPen('#bdbdbd'))
            axis.setTextPen(pg.mkPen('#424242'))
        self.live_curve = plot_item.plot([], [], pen=pen, symbol=None)
        
        # Disable auto range to avoid Qt6 compatibility issues
        try:
            plot_item.enableAutoRange('x', False)
            plot_item.enableAutoRange('y', False)
        except Exception:
            pass
        
        plot_group.setLayout(plot_layout)
        layout.addWidget(plot_group)

        # Blink detection controls (runtime diagnostic only)
        blink_group = QGroupBox("Blink Detection (diagnostic)")
        blink_layout = QHBoxLayout()
        self.blink_start_button = QPushButton("Start Blink Monitor")
        self.blink_stop_button = QPushButton("Stop Blink Monitor")
        self.blink_stop_button.setEnabled(False)
        self.blink_status = QLabel("Idle")
        self.blink_status.setStyleSheet(
            "padding: 4px 10px; border-radius: 6px; background-color: #e3f2fd; color: #0d47a1;"
        )
        self.blink_start_button.clicked.connect(self.start_blink_monitor)
        self.blink_stop_button.clicked.connect(self.stop_blink_monitor)
        blink_layout.addWidget(self.blink_start_button)
        blink_layout.addWidget(self.blink_stop_button)
        blink_layout.addWidget(self.blink_status)
        blink_group.setLayout(blink_layout)
        layout.addWidget(blink_group)
        
        # Log area
        log_group = QGroupBox("System Log")
        log_layout = QVBoxLayout()
        
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMaximumHeight(140)
        log_layout.addWidget(self.log_area)
        
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)
        
        self.tabs.addTab(tab, "Connection")

    def setup_analysis_tab(self):
        """Setup analysis and calibration tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(18)

        cal_group = QGroupBox()
        cal_layout = QGridLayout()
        cal_layout.setHorizontalSpacing(18)
        cal_layout.setVerticalSpacing(12)

        self.eyes_closed_button = QPushButton("Start Eyes Closed")
        self.eyes_closed_button.clicked.connect(lambda: self.start_calibration('eyes_closed'))
        self.eyes_closed_button.setEnabled(False)
        cal_layout.addWidget(self.eyes_closed_button, 0, 0)

        self.eyes_closed_label = QLabel("Status: Not started")
        cal_layout.addWidget(self.eyes_closed_label, 0, 1)

        self.eyes_open_button = QPushButton("Start Eyes Open")
        self.eyes_open_button.clicked.connect(lambda: self.start_calibration('eyes_open'))
        self.eyes_open_button.setEnabled(False)
        cal_layout.addWidget(self.eyes_open_button, 1, 0)

        self.eyes_open_label = QLabel("Status: Not started")
        cal_layout.addWidget(self.eyes_open_label, 1, 1)

        task_row = QHBoxLayout()
        task_row.setSpacing(12)
        task_label = QLabel("Task:")
        task_row.addWidget(task_label)

        self.task_combo = QComboBox()
        self.task_combo.addItems(list(AVAILABLE_TASKS.keys()))
        self.task_combo.currentTextChanged.connect(self.update_task_preview)
        task_row.addWidget(self.task_combo, 1)

        self.task_button = QPushButton("Start Task")
        self.task_button.clicked.connect(self.start_task)
        self.task_button.setEnabled(False)
        task_row.addWidget(self.task_button)

        cal_layout.addLayout(task_row, 2, 0, 1, 2)

        self.task_preview = QTextEdit()
        self.task_preview.setReadOnly(True)
        self.task_preview.setMinimumHeight(220)
        self.task_preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.task_preview.setStyleSheet(
            "background-color:#f8fbff; border:1px solid #dbeafe; border-radius:12px;"
        )
        cal_layout.addWidget(self.task_preview, 3, 0, 1, 2)

        self.task_label = QLabel("Status: Not started")
        self.task_label.setAlignment(Qt.AlignLeft)
        self.task_label.setStyleSheet(
            "padding:6px 12px; border-radius:10px; background:#eef2ff; color:#1e3a8a; font-weight:600;"
        )
        task_status_row = QHBoxLayout()
        task_status_row.setContentsMargins(0, 6, 0, 0)
        task_status_row.addWidget(self.task_label)
        task_status_row.addStretch()
        cal_layout.addLayout(task_status_row, 4, 0, 1, 2)

        stop_row = QHBoxLayout()
        stop_row.addStretch()
        self.stop_button = QPushButton("Stop Current Phase")
        self.stop_button.clicked.connect(self.stop_calibration)
        self.stop_button.setEnabled(False)
        stop_row.addWidget(self.stop_button)
        cal_layout.addLayout(stop_row, 5, 0, 1, 2)

        cal_group.setLayout(cal_layout)
        layout.addWidget(cal_group)

        status_row = QHBoxLayout()
        status_row.setSpacing(10)
        status_title = QLabel("Feature Pipeline:")
        status_title.setStyleSheet("font-weight:600; color:#4b5563;")
        status_row.addWidget(status_title)

        self.feature_status_label = QLabel("Idle")
        self.feature_status_label.setStyleSheet(
            "padding:6px 14px; border-radius:999px; background:#f1f5f9; color:#475569; font-weight:600;"
        )
        status_row.addWidget(self.feature_status_label)
        status_row.addStretch()
        layout.addLayout(status_row)

        self.analysis_summary = QTextEdit()
        self.analysis_summary.setReadOnly(True)
        self.analysis_summary.setVisible(False)
        self.analysis_summary.setPlaceholderText("Task insights will appear here once analysis completes.")
        self.analysis_summary.setMinimumHeight(140)
        layout.addWidget(self.analysis_summary)

        layout.addStretch()

        self.analysis_tab_index = self.tabs.addTab(tab, "Analysis")
    
    def setup_tasks_tab(self):
        """Setup streamlined multi-task overview tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(18)

        intro = QLabel("Run aggregated insights once you have completed individual task analyses.")
        intro.setWordWrap(True)
        intro.setStyleSheet("color:#4b5563;")
        layout.addWidget(intro)

        self.analyze_all_button = QPushButton("Analyze All Tasks")
        self.analyze_all_button.setFixedHeight(52)
        self.analyze_all_button.clicked.connect(self._handle_multi_task_analysis)
        layout.addWidget(self.analyze_all_button)

        self.generate_all_report_button = QPushButton("Generate Combined Report")
        self.generate_all_report_button.setFixedHeight(52)
        self.generate_all_report_button.clicked.connect(self._handle_multi_task_report)
        layout.addWidget(self.generate_all_report_button)

        self.multi_task_text = QTextEdit()
        self.multi_task_text.setReadOnly(True)
        self.multi_task_text.setVisible(False)
        self.multi_task_text.setPlaceholderText("Multi-task summaries will appear here once available.")
        layout.addWidget(self.multi_task_text)

        layout.addStretch()

        self.multi_task_tab_index = self.tabs.addTab(tab, "Multi-Task")

    def _handle_multi_task_analysis(self):
        """Placeholder multi-task analysis trigger."""
        self.log_message("Multi-task analysis coming soon.")
        QMessageBox.information(
            self,
            "Multi-Task Analysis",
            "Multi-task analytics will be available in an upcoming update."
        )

    def _handle_multi_task_report(self):
        """Placeholder multi-task reporting trigger."""
        self.log_message("Combined report generation coming soon.")
        QMessageBox.information(
            self,
            "Combined Report",
            "Multi-task reporting will be available in an upcoming update."
        )

    def handle_proceed_to_analysis(self):
        """Unlock the tasks tab and navigate to it."""
        self.tabs.setTabEnabled(self.analysis_tab_index, True)
        self.tabs.setCurrentIndex(self.analysis_tab_index)
        self.log_message("Moved to task flow. Begin calibrations to continue.")

    def _reset_workflow_progress(self):
        """Return the UI to the beginning of the guided flow."""
        self._tasks_complete = False
        try:
            self.tabs.setCurrentIndex(self.connection_tab_index)
        except Exception:
            pass
        try:
            self._calibration_timer.stop()
        except Exception:
            pass
        if hasattr(self, 'proceed_to_analysis_button'):
            self.proceed_to_analysis_button.setEnabled(False)

    def _set_feature_status(self, text: str, state: str = "idle") -> None:
        """Update the feature pipeline status pill."""
        palette = {
            "idle": ("#f1f5f9", "#475569"),
            "ready": ("#dcfce7", "#166534"),
            "collecting": ("#fef3c7", "#92400e"),
            "analyzing": ("#e0f2fe", "#075985"),
            "insights": ("#ede9fe", "#5b21b6"),
            "error": ("#fee2e2", "#991b1b"),
        }

        background, foreground = palette.get(state, palette["idle"])
        if hasattr(self, "feature_status_label"):
            self.feature_status_label.setText(text)
            self.feature_status_label.setStyleSheet(
                f"padding:6px 14px; border-radius:999px; background:{background}; color:{foreground}; font-weight:600;"
            )

    def _load_signal_file(self, which: str):
        """Load a 1D raw signal file (.npy preferred; .csv fallback)."""
        path, _ = QFileDialog.getOpenFileName(self, "Select Signal File", os.getcwd(), "Signal Files (*.npy *.csv)")
        if not path:
            return
        try:
            sig = None
            if path.lower().endswith('.npy'):
                sig = np.load(path)
            else:
                df = pd.read_csv(path)
                # use first numeric column
                for col in df.columns:
                    try:
                        vals = pd.to_numeric(df[col], errors='coerce').dropna().values
                        if vals.size > 0:
                            sig = vals
                            break
                    except Exception:
                        continue
            if sig is None:
                raise ValueError("No numeric column found in CSV")
            sig = np.asarray(sig).astype(float).ravel()
            if which == 'A':
                self._sessionA_signal = sig
                self.lbl_sig_A.setText(f"Signal: {os.path.basename(path)} | samples={sig.size} | fs={FS}")
            else:
                self._sessionB_signal = sig
                self.lbl_sig_B.setText(f"Signal B: {os.path.basename(path)} | samples={sig.size} | fs={FS}")
            self.log_message(f"Loaded signal ({which}) with {sig.size} samples")
            self._update_compare_button_state()
        except Exception as e:
            QMessageBox.warning(self, "Load Signal Failed", str(e))

    def _load_events_file(self, which: str):
        path, _ = QFileDialog.getOpenFileName(self, "Select Events File", os.getcwd(), "Label Files (*.csv *.json)")
        if not path:
            return
        try:
            evs = parse_events(path)
            if which == 'A':
                self._sessionA_events = evs
                self.lbl_evt_A.setText(f"Events: {os.path.basename(path)} | n={len(evs)}")
            else:
                self._sessionB_events = evs
                self.lbl_evt_B.setText(f"Events B: {os.path.basename(path)} | n={len(evs)}")
            self.log_message(f"Loaded events ({which}): {len(evs)} entries")
            self._update_compare_button_state()
        except Exception as e:
            QMessageBox.warning(self, "Load Events Failed", str(e))

    def _update_compare_button_state(self):
        ok = (self._sessionA_signal is not None and self._sessionA_events is not None and
              self._sessionB_signal is not None and self._sessionB_events is not None)
        self.btn_compare_AB.setEnabled(bool(ok))

    def _run_sessionA_analysis(self):
        if self._sessionA_signal is None or self._sessionA_events is None:
            QMessageBox.information(self, "Missing Data", "Please load Session A signal and events first.")
            return
        try:
            analyzer = TaskAnalyzer(base_module=sys.modules[__name__])
            resA = analyzer.analyze(self._sessionA_signal, self._sessionA_events)
            self._task_pipeline_results_A = resA
            report = render_task_report(resA)
            self.task_report_text.setPlainText(report)
            self.log_message("Session A analysis complete.")
        except Exception as e:
            QMessageBox.critical(self, "Analysis Error", str(e))

    def _run_two_session_agreement(self):
        if not (self._task_pipeline_results_A and self._sessionB_signal is not None and self._sessionB_events is not None):
            QMessageBox.information(self, "Missing Data", "Please analyze Session A and load Session B signal/events.")
            return
        try:
            analyzer = TaskAnalyzer(base_module=sys.modules[__name__])
            resB = analyzer.analyze(self._sessionB_signal, self._sessionB_events)
            self._task_pipeline_results_B = resB
            cos = TaskAnalyzer.two_session_cosine(self._task_pipeline_results_A, resB)
            repA = render_task_report(self._task_pipeline_results_A)
            repAgree = render_two_session_agreement(self._task_pipeline_results_A, resB, cos)
            self.task_report_text.setPlainText(repA + "\n\n" + repAgree)
            self.log_message("Two-session agreement computed.")
        except Exception as e:
            QMessageBox.critical(self, "Agreement Error", str(e))
    
    def setup_timers(self):
        """Setup update timers"""
        # Live plot update timer - match BrainCompanion.py frequency
        self.live_timer = QTimer(self)
        self.live_timer.timeout.connect(self.update_live_plot)
        self.live_timer.start(50)  # Update every 50ms like BrainCompanion.py
        
        # Features update timer
        self.features_timer = QTimer(self)
        self.features_timer.timeout.connect(self.update_features_display)
        self.features_timer.start(1000)  # Update every 1s

        # Blink monitor timer (created but inactive until user starts)
        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(200)  # 5 Hz check
        self._blink_timer.timeout.connect(self._blink_check)

        # Blink runtime state
        self._blink_active = False
        self._blink_last_ts = None
        self._blink_count = 0
        self._blink_window = deque(maxlen=512)  # 1s of data at 512Hz
        self._blink_threshold = None
        self._blink_recent_events = deque(maxlen=20)

    def start_blink_monitor(self):
        if self._blink_active:
            return
        self._blink_active = True
        self._blink_count = 0
        self._blink_window.clear()
        self._blink_threshold = None
        self._blink_recent_events.clear()
        self._blink_timer.start()
        self.blink_start_button.setEnabled(False)
        self.blink_stop_button.setEnabled(True)
        self.blink_status.setText("Running…")
        # Capture original background once for safe restoration
        try:
            if not hasattr(self, '_blink_orig_bg'):
                # backgroundBrush may return QBrush; fall back to string
                bg = getattr(self.plot_widget, 'backgroundBrush', lambda: None)()
                if bg and hasattr(bg, 'color'):
                    self._blink_orig_bg = bg.color().name()
                else:
                    self._blink_orig_bg = '#000000'
        except Exception:
            self._blink_orig_bg = '#000000'
        self.log_message("Blink monitor started")

    def stop_blink_monitor(self):
        if not self._blink_active:
            return
        self._blink_active = False
        self._blink_timer.stop()
        rate = 0.0
        try:
            # Approximate per-minute rate over monitoring session using event timestamps
            if self._blink_recent_events:
                duration = (self._blink_recent_events[-1] - self._blink_recent_events[0])
                if duration > 0:
                    rate = (len(self._blink_recent_events) - 1) / duration * 60.0
        except Exception:
            pass
        self.blink_status.setText(f"Stopped | Blinks: {self._blink_count} (~{rate:.1f}/min)")
        self.blink_start_button.setEnabled(True)
        self.blink_stop_button.setEnabled(False)
        # Restore original background color
        try:
            if hasattr(self, '_blink_orig_bg'):
                self.plot_widget.setBackground(self._blink_orig_bg)
        except Exception:
            pass
        self.log_message(f"Blink monitor stopped. Total blinks: {self._blink_count}")

    def _blink_check(self):
        # Lightweight blink detection: large transient absolute deviations
        if not self._blink_active:
            return
        global live_data_buffer
        if len(live_data_buffer) == 0:
            return
        # Update rolling window
        try:
            new_samples = live_data_buffer[-128:]  # recent ~250ms
            self._blink_window.extend(new_samples)
            if len(self._blink_window) < 64:
                return
            arr = np.array(self._blink_window, dtype=float)
            # High-pass like detrend (remove mean)
            arr = arr - np.mean(arr)
            mad = np.median(np.abs(arr - np.median(arr))) + 1e-9
            # Adaptive threshold initialization
            if self._blink_threshold is None:
                self._blink_threshold = 6.0 * mad
            # Gradually adapt threshold to signal scale
            self._blink_threshold = 0.98 * self._blink_threshold + 0.02 * (6.0 * mad)
            # Detect peaks beyond threshold (positive or negative)
            over = np.where(np.abs(arr[-64:]) > self._blink_threshold)[0]
            now = time.time()
            if over.size > 0:
                # Debounce: require 200ms since last blink
                if self._blink_last_ts is None or (now - self._blink_last_ts) > 0.2:
                    self._blink_last_ts = now
                    self._blink_count += 1
                    self._blink_recent_events.append(now)
                    self.blink_status.setText(f"Blink #{self._blink_count}")
                    # Briefly flash plot background for confirmation (non-invasive)
                    try:
                        orig = getattr(self, '_blink_orig_bg', '#000000')
                        self.plot_widget.setBackground('#202020')
                        QTimer.singleShot(120, lambda o=orig: self.plot_widget.setBackground(o))
                    except Exception:
                        pass
        except Exception as e:
            self.blink_status.setText(f"Blink err: {e}")
    
    def log_message(self, message):
        """Add timestamped message to log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_area.append(f"[{timestamp}] {message}")
        self.status_label.setText(message)
    
    def update_live_plot(self):
        """Update live plot with EEG data"""
        global live_data_buffer
        
        # Update plot with real data
        if len(live_data_buffer) >= 50:
            try:
                # Get the most recent data for plotting
                plot_size = min(256, len(live_data_buffer))
                data = np.array(live_data_buffer[-plot_size:])
                
                # Create x-axis (sample indices)
                x_data = np.arange(len(data))
                
                # Update the plot curve with visible line
                self.live_curve.setData(x_data, data)
                
                # Manually set Y range to avoid autoRangeEnabled error
                if len(data) > 0:
                    y_min, y_max = np.min(data), np.max(data)
                    y_range = y_max - y_min
                    padding = y_range * 0.1 if y_range > 0 else 50
                    
                    # Use plot item directly to avoid Qt6 compatibility issues
                    try:
                        plot_item = self.plot_widget.getPlotItem()
                        plot_item.setYRange(y_min - padding, y_max + padding, padding=0)
                        plot_item.setXRange(0, len(data), padding=0)
                    except Exception:
                        # Fallback to widget level if plot item access fails
                        self.plot_widget.setYRange(y_min - padding, y_max + padding, padding=0)
                        self.plot_widget.setXRange(0, len(data), padding=0)
                
                # Update status label
                if hasattr(self, 'status_label'):
                    self.status_label.setText(f"Buffer: {len(live_data_buffer)} samples | Latest: {live_data_buffer[-1]:.1f} µV | Range: {y_min:.1f} to {y_max:.1f} µV")
                
            except Exception as e:
                print(f"Plot update error: {e}")
                # Update status even if plot fails
                if hasattr(self, 'status_label') and len(live_data_buffer) > 0:
                    self.status_label.setText(f"Buffer: {len(live_data_buffer)} samples | Latest: {live_data_buffer[-1]:.1f} µV | Plot error: {e}")
        else:
            # Update status when not enough data
            if hasattr(self, 'status_label'):
                if len(live_data_buffer) > 0:
                    self.status_label.setText(f"Buffer: {len(live_data_buffer)} samples | Latest: {live_data_buffer[-1]:.1f} µV | Need {50 - len(live_data_buffer)} more samples")
                else:
                    self.status_label.setText("Waiting for data...")
    
    def update_features_display(self):
        """Update real-time features display"""
        if not self.feature_engine.latest_features:
            self._set_feature_status("Idle", "idle")
            return
        
        features = self.feature_engine.latest_features
        preview = ", ".join(list(features.keys())[:3])
        badge_text = f"Streaming {len(features)} features" if features else "Collecting"
        self._set_feature_status(badge_text, "collecting")
        if preview:
            self.status_label.setText(f"Live features: {preview}...")
    
    def on_connect_clicked(self):
        """Connect to MindLink device with authentication"""
        global BACKEND_URL, SERIAL_PORT, ALLOWED_HWIDS
        
        # Set backend URL based on environment
        if self.radio_en.isChecked():
            BACKEND_URL = BACKEND_URLS["en"]
            login_url = LOGIN_URLS["en"]
            self.log_message("Using EN environment")
        elif self.radio_nl.isChecked():
            BACKEND_URL = BACKEND_URLS["nl"]
            login_url = LOGIN_URLS["nl"]
            self.log_message("Using NL environment")
        else:
            BACKEND_URL = BACKEND_URLS["local"]
            login_url = LOGIN_URLS["local"]
            self.log_message("Using local environment")
        
        # Login dialog
        login_dialog = LoginDialog(self)
        if login_dialog.exec() == QDialog.Accepted:
            username, password = login_dialog.get_credentials()
            
            # Authentication exactly like mother code
            login_payload = {
                "username": username,
                "password": password
            }
            
            try:
                self.log_message(f"Connecting to {login_url}")
                
                # First try with certificate verification
                try:
                    login_response = requests.post(
                        login_url, 
                        json=login_payload,
                        headers={"Content-Type": "application/json"},
                        timeout=10,
                        verify=True
                    )
                except requests.exceptions.ProxyError as e:
                    self.log_message(f"Proxy error: {str(e)}. Retrying without proxy...")
                    direct_session = requests.Session()
                    direct_session.proxies = {}
                    login_response = direct_session.post(
                        login_url, 
                        json=login_payload,
                        headers={"Content-Type": "application/json"},
                        timeout=10,
                        verify=True
                    )
                
                if login_response.status_code == 200:
                    data = login_response.json()
                    self.jwt_token = data.get("x-jwt-access-token")
                    hwid = data.get("hwid")
                    
                    if self.jwt_token:
                        self.log_message("✓ Login successful. JWT token obtained.")
                        if hwid:
                            self.log_message(f"✓ Hardware ID received: {hwid}")
                            ALLOWED_HWIDS = [hwid]
                    else:
                        self.log_message("✗ Login response didn't contain expected token.")
                        return
                else:
                    # Try without certificate verification
                    self.log_message("Trying without SSL verification...")
                    login_response = requests.post(
                        login_url, 
                        json=login_payload,
                        headers={"Content-Type": "application/json"},
                        timeout=10,
                        verify=False
                    )
                    
                    if login_response.status_code == 200:
                        data = login_response.json()
                        self.jwt_token = data.get("x-jwt-access-token")
                        hwid = data.get("hwid")
                        
                        if self.jwt_token:
                            self.log_message("✓ Login successful (without SSL verification).")
                            if hwid:
                                self.log_message(f"✓ Hardware ID received: {hwid}")
                                ALLOWED_HWIDS = [hwid]
                        else:
                            self.log_message("✗ Login failed.")
                            return
                    else:
                        self.log_message(f"✗ Login failed: {login_response.status_code}")
                        return
                        
            except Exception as e:
                self.log_message(f"Login error: {str(e)}")
                return
        else:
            self.log_message("Login cancelled.")
            return
        
        # After successful login, fetch user-specific HWIDs like in mother code
        api_base = BACKEND_URL.replace("/brainlink_data", "")
        try:
            hwids_url = f"{api_base}/users/hwids"
            self.log_message(f"Fetching authorized device IDs from {hwids_url}")
            hwid_response = requests.get(
                hwids_url,
                headers = {"X-Authorization": f"Bearer {self.jwt_token}"},
                timeout=5
            )
            if hwid_response.status_code == 200:
                # Normalize HWID data to a list
                raw_hwids = hwid_response.json().get("brainlink_hwid", [])
                if isinstance(raw_hwids, str):
                    ALLOWED_HWIDS = [raw_hwids]
                elif isinstance(raw_hwids, list):
                    ALLOWED_HWIDS = raw_hwids
                else:
                    ALLOWED_HWIDS = []
                self.log_message(f"✓ Fetched {len(ALLOWED_HWIDS)} authorized device IDs")
                if ALLOWED_HWIDS:
                    self.log_message(f"✓ Authorized HWIDs: {ALLOWED_HWIDS}")
            else:
                self.log_message(f"✗ Failed to fetch HWIDs ({hwid_response.status_code}); using default detection")
        except Exception as e:
            self.log_message(f"Error fetching HWIDs: {e}")
        
        # Detect and connect to device
        SERIAL_PORT = detect_brainlink()
        if not SERIAL_PORT:
            self.log_message("✗ No MindLink device found!")
            return
        
        self.log_message(f"✓ Found MindLink device: {SERIAL_PORT}")
        
        # Start MindLink connection
        try:
            self.serial_obj = CushySerial(SERIAL_PORT, SERIAL_BAUD)
            self.log_message("Starting MindLink thread...")
            
            global stop_thread_flag
            stop_thread_flag = False
            
            self.brainlink_thread = threading.Thread(target=run_brainlink, args=(self.serial_obj,))
            self.brainlink_thread.daemon = True
            self.brainlink_thread.start()
            
            self.connect_button.setEnabled(False)
            self.disconnect_button.setEnabled(True)
            
            # Enable calibration buttons
            self.eyes_closed_button.setEnabled(True)
            self.eyes_open_button.setEnabled(True)
            self.task_button.setEnabled(True)
            self._set_feature_status("Waiting for calibration", "idle")
            self._reset_workflow_progress()
            self.proceed_to_analysis_button.setEnabled(True)

            self.log_message("✓ MindLink connected successfully!")
            
        except Exception as e:
            self.log_message(f"✗ Failed to connect: {str(e)}")
    
    def on_disconnect_clicked(self):
        """Disconnect from MindLink device"""
        global stop_thread_flag, live_data_buffer
        stop_thread_flag = True
        
        # Clear session data - CRITICAL FIX for data persistence issue
        live_data_buffer.clear()
        print("Session data cleared: live_data_buffer reset")
        
        if self.serial_obj and self.serial_obj.is_open:
            self.serial_obj.close()
        
        if self.brainlink_thread and self.brainlink_thread.is_alive():
            self.brainlink_thread.join(timeout=2)
        
        # Reset feature engine state
        if hasattr(self, 'feature_engine') and self.feature_engine:
            self.feature_engine.reset_session()
        
        # Clear plot displays
        if hasattr(self, 'plot_widget') and self.plot_widget:
            try:
                self.plot_widget.clear()
            except Exception as e:
                print(f"Error clearing plot: {e}")
        
        self.connect_button.setEnabled(True)
        self.disconnect_button.setEnabled(False)
        
        # Disable calibration buttons
        self.eyes_closed_button.setEnabled(False)
        self.eyes_open_button.setEnabled(False)
        self.task_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self._set_feature_status("Idle", "idle")
        self._reset_workflow_progress()
        
        self.log_message("✓ Disconnected from MindLink device - Session data cleared")
    
    def start_calibration(self, phase_name):
        """Start calibration phase"""
        if self.feature_engine.current_state != 'idle':
            self.log_message("Please stop current phase first")
            return
        
        try:
            self._calibration_timer.stop()
        except Exception:
            pass

        self.feature_engine.start_calibration_phase(phase_name)
        self.stop_button.setEnabled(True)
        self._set_feature_status("Collecting baseline" if phase_name != 'task' else "Collecting task data", "collecting")
        
        if phase_name == 'eyes_closed':
            self.eyes_closed_label.setText("Status: Recording...")
            self.eyes_closed_button.setEnabled(False)
            self._calibration_timer.start(30_000)
        elif phase_name == 'eyes_open':
            self.eyes_open_label.setText("Status: Recording...")
            self.eyes_open_button.setEnabled(False)
            self._calibration_timer.start(30_000)
        
        self.log_message(f"✓ Started {phase_name} calibration")
    
    def update_task_preview(self, task_name):
        """Update task preview when selection changes"""
        if not task_name or task_name not in AVAILABLE_TASKS:
            self.task_preview.setHtml("<p><i>Select a task to see its description</i></p>")
            return
            
        task_config = AVAILABLE_TASKS[task_name]
        task_display_name = task_config.get('name', task_name.upper())
        description = task_config.get('description', 'No description available')
        instructions = task_config.get('instructions', 'No instructions available')
        duration = task_config.get('duration', 'Unknown')
        
        # Create user-friendly descriptions
        user_friendly_descriptions = {
            'emotion_face': {
                'overview': 'You will view 6 different emotional face images. For each face, you will have time to look at it and identify the emotion, then write down what emotion you observed.',
                'what_to_expect': '• A countdown to get ready<br>• An instruction to identify the emotion<br>• A face image to view for 3 seconds<br>• Time to write down the emotion you saw',
                'duration_note': f'{duration} seconds total (about 1 minute)'
            },
            'curiosity': {
                'overview': 'You will watch a short video clip designed to trigger curiosity. Simply watch and let yourself naturally respond to the content.',
                'what_to_expect': '• A brief introduction<br>• A video clip to watch<br>• Just relax and watch naturally',
                'duration_note': f'About {duration} seconds'
            },
            'reappraisal': {
                'overview': 'You will read different scenarios and practice thinking about them in either positive or negative ways, depending on the instruction.',
                'what_to_expect': '• A countdown to get ready<br>• Instructions to "Think Positive" or "Focus on Negatives"<br>• A scenario to read<br>• Time to think about it as instructed',
                'duration_note': f'About {duration} seconds total'
            },
            'diverse_thinking': {
                'overview': 'You will see creative prompts and think of as many different uses or ideas as possible. Let your creativity flow!',
                'what_to_expect': '• A countdown to get ready<br>• A creative prompt (like "uses for a paperclip")<br>• Time to think creatively about the prompt',
                'duration_note': f'About {duration} seconds total'
            }
        }
        
        friendly_info = user_friendly_descriptions.get(task_name, {
            'overview': description,
            'what_to_expect': f'Follow the instructions: {instructions}',
            'duration_note': f'Duration: {duration} seconds'
        })
        
        preview_html = f"""
        <div style="font-family: Arial, sans-serif; line-height: 1.4;">
            <h3 style="color: #2c3e50; margin-top: 0;">{task_display_name}</h3>
            <p><strong>Example: What you'll do:</strong><br>{friendly_info['overview']}</p>
            <p><strong>Example: What to expect:</strong><br>{friendly_info['what_to_expect']}</p>
            <p><strong>Time:</strong> {friendly_info['duration_note']}</p>
            <p style="font-size: 11px; color: #666; margin-bottom: 0;">
                <em>💡 Don't worry about the details now - you'll get clear instructions during the task!</em>
            </p>
        </div>
        """
        
        self.task_preview.setHtml(preview_html)

    def start_task(self):
        """Start task calibration"""
        if self.feature_engine.current_state != 'idle':
            self.log_message("Please stop current phase first")
            return
        
        task_type = self.task_combo.currentText()
        self.feature_engine.start_calibration_phase('task', task_type)
        
        self.task_label.setText(f"Status: Recording {task_type}...")
        self.task_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self._set_feature_status("Collecting task data", "collecting")
        
        self.log_message(f"✓ Started task: {task_type}")
        
        # Show interactive task interface
        self.show_task_interface(task_type)
    
    def stop_calibration(self):
        """Stop current calibration phase"""
        if self.feature_engine.current_state == 'idle':
            return
        
        try:
            self._calibration_timer.stop()
        except Exception:
            pass

        phase = self.feature_engine.current_state
        self.feature_engine.stop_calibration_phase()
        
        self.stop_button.setEnabled(False)
        
        if phase == 'eyes_closed':
            self.eyes_closed_label.setText("Status: Completed")
            self.eyes_closed_button.setEnabled(True)
        elif phase == 'eyes_open':
            self.eyes_open_label.setText("Status: Completed")
            self.eyes_open_button.setEnabled(True)
        elif phase == 'task':
            self.task_label.setText("Status: Completed")
            self.task_button.setEnabled(True)
            # Close task interface if it exists
            self.close_task_interface()
        
        self.log_message(f"✓ Stopped {phase} calibration")

        if (len(self.feature_engine.calibration_data['eyes_closed']['features']) > 0 and
                len(self.feature_engine.calibration_data['eyes_open']['features']) > 0):
            self.compute_baseline()

        if phase == 'task' and len(self.feature_engine.calibration_data['task']['features']) > 0:
            self._set_feature_status("Analyzing task", "analyzing")
            self.analyze_task()
        elif self.feature_engine.current_state == 'idle':
            self._set_feature_status("Idle", "idle")

    def _auto_stop_calibration(self):
        """Automatically stop baseline phases after the default capture window."""
        phase = getattr(self.feature_engine, 'current_state', None)
        if phase in {"eyes_closed", "eyes_open"}:
            self.log_message(f"Auto-stopping {phase} calibration after 30 seconds.")
            try:
                self.stop_calibration()
            except Exception:
                self.log_message(f"Auto-stop failed for {phase} calibration")
    
    def compute_baseline_statistics(self):
        """Compute baseline statistics"""
        baseline_features = []
        baseline_features.extend(self.calibration_data['eyes_closed']['features'])
        baseline_features.extend(self.calibration_data['eyes_open']['features'])
        
        if len(baseline_features) == 0:
            return
        
        df = pd.DataFrame(baseline_features)
        self.baseline_stats = {}
        
        for feature in FEATURE_NAMES:
            if feature in df.columns:
                values = df[feature].values
                self.baseline_stats[feature] = {
                    'mean': np.mean(values),
                    'std': np.std(values),
                    'min': np.min(values),
                    'max': np.max(values),
                    'median': np.median(values),
                    'q25': np.percentile(values, 25),
                    'q75': np.percentile(values, 75)
                }
        
        print(f"Baseline statistics computed for {len(self.baseline_stats)} features")
    
    def analyze_task_data(self):
        """Analyze task data against baseline"""
        if not self.baseline_stats:
            return
        
        task_features = self.calibration_data['task']['features']
        if len(task_features) == 0:
            return
        
        task_df = pd.DataFrame(task_features)
        self.analysis_results = {}
        
        for feature in FEATURE_NAMES:
            if feature in task_df.columns and feature in self.baseline_stats:
                task_values = task_df[feature].values
                baseline_mean = self.baseline_stats[feature]['mean']
                baseline_std = self.baseline_stats[feature]['std']
                
                z_scores = (task_values - baseline_mean) / (baseline_std + 1e-10)
                outliers = np.abs(z_scores) > 2
                
                self.analysis_results[feature] = {
                    'task_mean': np.mean(task_values),
                    'task_std': np.std(task_values),
                    'baseline_mean': baseline_mean,
                    'baseline_std': baseline_std,
                    'z_scores': z_scores,
                    'outliers': outliers,
                    'outlier_percentage': np.sum(outliers) / len(outliers) * 100,
                    'significant_change': abs(np.mean(task_values) - baseline_mean) > 2 * baseline_std
                }
        
        print(f"Task analysis completed for {len(self.analysis_results)} features")
        return self.analysis_results
    
    def log_message(self, message):
        """Add timestamped message to log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_area.append(f"[{timestamp}] {message}")
        self.status_label.setText(message)
    
    def update_features_display(self):
        """Update real-time features display"""
        if not self.feature_engine.latest_features:
            return
        
        features = self.feature_engine.latest_features
        preview = ", ".join(
            f"{name}: {value:.3f}" for name, value in list(features.items())[:4]
        )
        if preview:
            self.status_label.setText(f"Live features — {preview}")

    def handle_extended_eeg_from_packet(self, data: Any) -> None:
        """Receive extended EEG telemetry and update battery widgets."""
        battery_val = getattr(data, 'battery', None)
        firmware = getattr(data, 'version', None)
        try:
            if battery_val is not None:
                battery_val = int(float(battery_val))
        except Exception:
            battery_val = None
        self.battery_update.emit(battery_val, firmware)

    def _battery_stylesheet(self, level: Optional[int]) -> str:
        if level is None:
            chunk = "#94a3b8"
        elif level >= 60:
            chunk = "#16a34a"
        elif level >= 30:
            chunk = "#f59e0b"
        else:
            chunk = "#dc2626"
        return (
            "QProgressBar {"
            " background-color: #f1f5f9;"
            " border: 1px solid #d0d7de;"
            " border-radius: 6px;"
            " padding: 0;"
            " }"
            "QProgressBar::chunk {"
            f" background-color: {chunk};"
            " border-radius: 5px;"
            " }"
        )

    def _build_battery_indicator(self) -> QWidget:
        container = QWidget()
        container.setObjectName("BatteryIndicator")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(2)

        label = QLabel("Battery --%")
        label.setStyleSheet("color:#475569; font-size:10px; font-weight:600;")
        progress = QProgressBar()
        progress.setRange(0, 100)
        progress.setValue(0)
        progress.setTextVisible(False)
        progress.setFixedHeight(10)
        progress.setFixedWidth(110)
        progress.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        progress.setStyleSheet(self._battery_stylesheet(None))

        layout.addWidget(label, alignment=Qt.AlignLeft)
        layout.addWidget(progress)

        container.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)

        entry: Dict[str, Any] = {
            'container': container,
            'label': label,
            'progress': progress,
        }
        self._battery_widgets.append(entry)

        if self._primary_battery_entry is None:
            self._primary_battery_entry = entry
            self._battery_widget = container
            self.battery_status_label = label
            self.battery_progress = progress

        def _cleanup(_obj=None, entry_ref=entry):
            try:
                if entry_ref in self._battery_widgets:
                    self._battery_widgets.remove(entry_ref)
            except Exception:
                pass
            if self._primary_battery_entry is entry_ref:
                self._primary_battery_entry = self._battery_widgets[0] if self._battery_widgets else None
                primary = self._primary_battery_entry
                if primary is not None:
                    self._battery_widget = primary.get('container')
                    self.battery_status_label = primary.get('label')
                    self.battery_progress = primary.get('progress')
                else:
                    self._battery_widget = None
                    self.battery_status_label = None
                    self.battery_progress = None

        try:
            container.destroyed.connect(_cleanup)
        except Exception:
            pass

        default_tip = "Battery telemetry will appear once the headset streams data."
        for widget in (container, label, progress):
            try:
                widget.setToolTip(default_tip)
            except Exception:
                pass

        if self._pending_battery_update is not None:
            pending = self._pending_battery_update
            self._pending_battery_update = None
            self._apply_battery_update(*pending)
        else:
            self._apply_battery_update(self._battery_level, self._battery_version)

        return container

    def _apply_battery_update(self, level: Optional[int], version: Optional[Any]) -> None:
        if level is not None:
            try:
                level = max(0, min(100, int(level)))
            except Exception:
                level = None
        if level is not None:
            self._battery_level = level
        if version is not None:
            self._battery_version = version

        if not self._battery_widgets:
            self._pending_battery_update = (self._battery_level, self._battery_version)
            return

        self._pending_battery_update = None

        tooltip = "Battery telemetry unavailable."
        if level is not None:
            tooltip = f"Battery level {level}%"
            if version is not None:
                tooltip = f"{tooltip} — firmware {version}"
        elif version is not None:
            tooltip = f"Firmware {version}"

        label_text = "Battery --%" if level is None else f"Battery {level}%"
        progress_value = level if level is not None else 0
        progress_style = self._battery_stylesheet(level)

        invalid_entries: List[Dict[str, Any]] = []
        for entry in self._battery_widgets:
            try:
                label = entry.get('label')
                bar = entry.get('progress')
                container = entry.get('container')
                if bar is not None:
                    bar.setValue(progress_value)
                    bar.setStyleSheet(progress_style)
                if label is not None:
                    label.setText(label_text)
                for widget in (container, label, bar):
                    if widget is not None:
                        widget.setToolTip(tooltip)
            except RuntimeError:
                invalid_entries.append(entry)
            except Exception:
                continue

        for bad in invalid_entries:
            try:
                self._battery_widgets.remove(bad)
            except ValueError:
                pass

        if self.battery_status_label is not None:
            try:
                self.battery_status_label.setText(label_text)
                self.battery_status_label.setToolTip(tooltip)
            except Exception:
                self.battery_status_label = None
        if self.battery_progress is not None:
            try:
                self.battery_progress.setValue(progress_value)
                self.battery_progress.setStyleSheet(progress_style)
                self.battery_progress.setToolTip(tooltip)
            except Exception:
                self.battery_progress = None

    def _center_task_dialog(self) -> None:
        dialog = self._active_task_dialog
        if dialog is None:
            return
        try:
            if not dialog.isVisible():
                return
        except RuntimeError:
            self._active_task_dialog = None
            return
        center = self.mapToGlobal(self.rect().center())
        frame = dialog.frameGeometry()
        frame.moveCenter(center)
        dialog.move(frame.topLeft())

    def resizeEvent(self, event):  # type: ignore[override]
        super().resizeEvent(event)
        overlay = self._task_overlay
        if overlay is not None:
            try:
                overlay.setGeometry(self.rect())
                overlay.raise_()
            except RuntimeError:
                self._task_overlay = None
        dialog = self._active_task_dialog
        if dialog is not None:
            try:
                dialog.raise_()
            except RuntimeError:
                self._active_task_dialog = None
        self._center_task_dialog()

    def closeEvent(self, event):  # type: ignore[override]
        try:
            ref = getattr(BrainLinkAnalyzerWindow, '_active_window', None)
            if ref and ref() is self:
                BrainLinkAnalyzerWindow._active_window = None
        except Exception:
            pass
        try:
            self.close_task_interface()
        except Exception:
            pass
        super().closeEvent(event)

    def show_task_interface(self, task_type):
        """Show interactive task guidance with a modal overlay."""
        self.close_task_interface()

        task_config = AVAILABLE_TASKS.get(task_type)
        if not task_config:
            self.log_message(f"⚠ Unknown task configuration: {task_type}")
            return

        try:
            overlay = QFrame(self)
            overlay.setObjectName("TaskModalOverlay")
            overlay.setStyleSheet("background-color: rgba(15, 23, 42, 170);")
            overlay.setGeometry(self.rect())
            overlay.setAttribute(Qt.WA_TransparentForMouseEvents, False)
            overlay.show()
            overlay.raise_()
            self._task_overlay = overlay

            def _overlay_click(_event):
                try:
                    if self._active_task_dialog is not None:
                        self._active_task_dialog.raise_()
                except Exception:
                    pass

            try:
                overlay.mousePressEvent = _overlay_click  # type: ignore[assignment]
            except Exception:
                pass

            dialog = QDialog(self)
            dialog.setObjectName("TaskGuidanceDialog")
            dialog.setModal(True)
            dialog.setWindowFlag(Qt.FramelessWindowHint, True)
            dialog.setWindowFlag(Qt.Dialog, True)
            dialog.setAttribute(Qt.WA_DeleteOnClose)
            apply_modern_dialog_theme(dialog)

            dialog_layout = QVBoxLayout(dialog)
            dialog_layout.setContentsMargins(28, 24, 28, 24)
            dialog_layout.setSpacing(16)

            title = QLabel(task_config.get('name', task_type.replace('_', ' ').title()))
            title.setStyleSheet("font-size:18px; font-weight:600; color:#0f172a;")
            dialog_layout.addWidget(title, alignment=Qt.AlignLeft)

            summary = QLabel(task_config.get('description', "Follow the on-screen instructions."))
            summary.setWordWrap(True)
            summary.setStyleSheet("color:#475569; font-size:13px;")
            dialog_layout.addWidget(summary)

            instruction_blocks: List[str] = []
            instructions = task_config.get('instructions')
            if instructions:
                instruction_blocks.append(instructions)

            phase_structure = task_config.get('phase_structure') or []
            if phase_structure:
                phase_lines = []
                for idx, phase in enumerate(phase_structure, start=1):
                    phase_type = phase.get('type', f'STEP {idx}').upper()
                    phase_duration = phase.get('duration')
                    phase_inst = phase.get('instruction', '')
                    duration_note = f" ({phase_duration}s)" if phase_duration else ""
                    phase_lines.append(f"<b>{phase_type}</b>{duration_note}: {phase_inst}")
                if phase_lines:
                    instruction_blocks.append("<br>".join(phase_lines))

            duration = task_config.get('duration')
            if duration:
                instruction_blocks.append(f"Estimated duration: {duration} seconds.")

            if instruction_blocks:
                instructions_label = QLabel("<br><br>".join(instruction_blocks))
                instructions_label.setTextFormat(Qt.RichText)
                instructions_label.setWordWrap(True)
                instructions_label.setStyleSheet("color:#0f172a; font-size:13px;")
                dialog_layout.addWidget(instructions_label)

            # Add signal quality indicator
            signal_quality_label = QLabel("Signal quality: Checking...")
            signal_quality_label.setStyleSheet(
                "font-size: 12px; "
                "padding: 8px 12px; "
                "border-radius: 6px; "
                "background-color: #f1f5f9; "
                "color: #64748b;"
            )
            signal_quality_label.setAlignment(Qt.AlignCenter)
            dialog_layout.addWidget(signal_quality_label)
            
            # Store reference for updates
            dialog._signal_quality_label = signal_quality_label
            
            # Create timer for signal quality updates
            signal_timer = QTimer(dialog)
            
            def update_signal_quality():
                try:
                    if hasattr(self, 'live_data_buffer') and len(self.live_data_buffer) > 100:
                        recent_data = list(self.live_data_buffer)[-100:]
                        if self._is_signal_noisy(recent_data, threshold_std=200):
                            signal_quality_label.setText("⚠ Signal: Check contact")
                            signal_quality_label.setStyleSheet(
                                "font-size: 12px; padding: 8px 12px; border-radius: 6px; "
                                "background-color: #fef2f2; color: #dc2626; font-weight: 600;"
                            )
                        else:
                            signal_quality_label.setText("✓ Signal: Good")
                            signal_quality_label.setStyleSheet(
                                "font-size: 12px; padding: 8px 12px; border-radius: 6px; "
                                "background-color: #f0fdf4; color: #16a34a; font-weight: 600;"
                            )
                    else:
                        signal_quality_label.setText("○ Signal: Waiting...")
                        signal_quality_label.setStyleSheet(
                            "font-size: 12px; padding: 8px 12px; border-radius: 6px; "
                            "background-color: #f1f5f9; color: #64748b;"
                        )
                except Exception as e:
                    pass
            
            signal_timer.timeout.connect(update_signal_quality)
            signal_timer.start(500)  # Update every 500ms
            dialog._signal_timer = signal_timer

            button_row = QHBoxLayout()
            button_row.setSpacing(12)
            button_row.addStretch()

            if hasattr(self, 'stop_button') and self.stop_button is not None:
                stop_task_btn = QPushButton("Stop Task")
                stop_task_btn.clicked.connect(self.stop_button.click)
                button_row.addWidget(stop_task_btn)

            dismiss_btn = QPushButton("Dismiss")
            dismiss_btn.setDefault(True)
            dismiss_btn.clicked.connect(dialog.accept)
            button_row.addWidget(dismiss_btn)

            dialog_layout.addLayout(button_row)

            dialog.finished.connect(self.close_task_interface)
            dialog.show()
            if overlay is not None:
                overlay.raise_()
            dialog.raise_()
            try:
                dialog.activateWindow()
            except Exception:
                pass

            self._active_task_dialog = dialog
            self._active_task_type = task_type
            self._center_task_dialog()
        except Exception as exc:
            self.log_message(f"⚠ Failed to display task dialog: {exc}")
            self.close_task_interface()

    def close_task_interface(self):
        """Close any active task dialog and remove the overlay."""
        dialog = self._active_task_dialog
        overlay = self._task_overlay

        self._active_task_dialog = None
        self._task_overlay = None
        self._active_task_type = None

        if overlay is not None:
            try:
                overlay.deleteLater()
            except Exception:
                pass

        if dialog is not None:
            # Stop signal quality timer if it exists
            if hasattr(dialog, '_signal_timer') and dialog._signal_timer is not None:
                try:
                    dialog._signal_timer.stop()
                    dialog._signal_timer.deleteLater()
                except Exception:
                    pass
            
            try:
                dialog.finished.disconnect(self.close_task_interface)
            except Exception:
                pass
            try:
                if dialog.isVisible():
                    dialog.close()
            except RuntimeError:
                pass
            except Exception:
                pass
            try:
                dialog.deleteLater()
            except Exception:
                pass
    
    def compute_baseline(self):
        """Compute baseline statistics"""
        self.feature_engine.compute_baseline_statistics()
        self._set_feature_status("Baseline ready", "ready")
        self.analysis_summary.clear()
        self.analysis_summary.setVisible(False)
        self.log_message("✓ Baseline statistics computed")
    
    def analyze_task(self):
        """Analyze task data"""
        results = self.feature_engine.analyze_task_data()
        if results:
            self.update_results_display(results)
            self._set_feature_status("Insights ready", "insights")
    
    def update_results_display(self, results):
        """Render analysis insights in the summary panel."""
        self.analysis_results = results
        lines = ["Feature Insights", ""]

        for feature, data in results.items():
            significant = "Significant change" if data['significant_change'] else "No significant change"
            lines.append(
                f"• {feature}: task μ {data['task_mean']:.3f} vs baseline μ {data['baseline_mean']:.3f}"
            )
            lines.append(
                f"    σ_task {data['task_std']:.3f}, σ_base {data['baseline_std']:.3f} — {significant}"
            )

        summary_text = "\n".join(lines)
        self.analysis_summary.setPlainText(summary_text)
        self.analysis_summary.setVisible(True)
        self._tasks_complete = True
        self.tabs.setTabEnabled(self.multi_task_tab_index, True)
        self.tabs.setCurrentIndex(self.multi_task_tab_index)
        self.log_message("✓ Task analysis completed. Multi-task summary unlocked.")
    
    def generate_report(self):
        """Generate analysis report"""
        report = "MindLink Feature Analysis Report\n"
        report += "=" * 50 + "\n\n"
        
        # Add baseline statistics
        if hasattr(self.feature_engine, 'baseline_stats'):
            report += "Baseline Statistics:\n"
            report += "-" * 20 + "\n"
            for feature, stats in self.feature_engine.baseline_stats.items():
                report += f"{feature}: Mean={stats['mean']:.4f}, Std={stats['std']:.4f}\n"
            report += "\n"
        
        # Add task analysis
        if hasattr(self.feature_engine, 'analysis_results'):
            report += "Task Analysis Results:\n"
            report += "-" * 20 + "\n"
            for feature, results in self.feature_engine.analysis_results.items():
                if results['significant_change']:
                    report += f"{feature}: SIGNIFICANT CHANGE - "
                    report += f"Task Mean={results['task_mean']:.4f}, "
                    report += f"Baseline Mean={results['baseline_mean']:.4f}\n"
        
        self.analysis_summary.setPlainText(report)
        self.analysis_summary.setVisible(True)
        self.log_message("✓ Report generated")


# --- Main execution ---
if __name__ == "__main__":
    import random
    
    # OS Selection
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    # Show OS selection dialog
    os_dialog = OSSelectionDialog()
    if os_dialog.exec() == QDialog.Accepted:
        selected_os = os_dialog.get_selected_os()
        
        # Create and show main window
        window = BrainLinkAnalyzerWindow(selected_os)
        window.show()
        
        sys.exit(app.exec())
    else:
        sys.exit(0)
