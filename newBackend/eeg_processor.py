"""
eeg_processor.py — TGAM byte-stream parser and digital EEG filter chain.

Implements the same algorithm as main.js (Electron) so both frontends produce
identical filtered waveforms.

TGAM packet codes (NeuroSky / BrainLink chip)
──────────────────────────────────────────────
0x02  POOR_SIGNAL  1-byte   0=perfect, 200=not worn
0x04  ATTENTION    1-byte   0–100
0x05  MEDITATION   1-byte   0–100
0x80  RAW_EEG      2-byte   int16 big-endian  (~512 Hz ADC)
0x83  EEG_POWER    24-byte  8 × uint24 big-endian band powers
0x85  EXTENDED     n-byte   byte[0]=battery%, byte[1-2]=firmware version
"""

import math
from typing import Callable, Dict, List, Optional

# ─── TGAM byte codes ──────────────────────────────────────────────────────────
CODE_POOR_SIGNAL = 0x02
CODE_ATTENTION   = 0x04
CODE_MEDITATION  = 0x05
CODE_RAW_EEG     = 0x80
CODE_EEG_POWER   = 0x83
CODE_EXTENDED    = 0x85

# Band order as defined by NeuroSky TGAM 0x83 packet
BAND_NAMES = [
    "delta", "theta",
    "lowAlpha", "highAlpha",
    "lowBeta",  "highBeta",
    "lowGamma", "midGamma",
]


# ─── Digital biquad filter ────────────────────────────────────────────────────

class Biquad:
    """Direct-Form I second-order IIR section."""

    def __init__(self, b0: float, b1: float, b2: float, a1: float, a2: float) -> None:
        self.b0, self.b1, self.b2 = b0, b1, b2
        self.a1, self.a2 = a1, a2
        self.x1 = self.x2 = self.y1 = self.y2 = 0.0

    def process(self, x: float) -> float:
        y = (self.b0 * x + self.b1 * self.x1 + self.b2 * self.x2
             - self.a1 * self.y1 - self.a2 * self.y2)
        self.x2 = self.x1
        self.x1 = x
        self.y2 = self.y1
        self.y1 = y
        return y


def create_eeg_filter(fs: float = 512.0) -> Callable[[float], float]:
    """
    Cascaded Butterworth biquad chain:
      HPF 1 Hz  → removes DC / slow drift
      LPF 45 Hz → removes EMG and high-frequency noise
      Notch 50 Hz (Q=35) → removes power-line interference

    Matches the JS implementation in main.js exactly.
    """
    S2 = math.sqrt(2)

    # High-pass at 1 Hz
    kH = math.tan(math.pi * 1.0 / fs)
    nH = 1.0 / (1.0 + S2 * kH + kH * kH)
    hpf = Biquad(
        nH, -2.0 * nH, nH,
        2.0 * (kH * kH - 1.0) * nH,
        (1.0 - S2 * kH + kH * kH) * nH,
    )

    # Low-pass at 45 Hz
    kL = math.tan(math.pi * 45.0 / fs)
    nL = 1.0 / (1.0 + S2 * kL + kL * kL)
    lpf = Biquad(
        kL * kL * nL, 2.0 * kL * kL * nL, kL * kL * nL,
        2.0 * (kL * kL - 1.0) * nL,
        (1.0 - S2 * kL + kL * kL) * nL,
    )

    # IIR notch at 50 Hz, Q = 35
    w0    = 2.0 * math.pi * 50.0 / fs
    cosW0 = math.cos(w0)
    alpha = math.sin(w0) / (2.0 * 35.0)
    a0n   = 1.0 + alpha
    notch = Biquad(
        1.0 / a0n, -2.0 * cosW0 / a0n, 1.0 / a0n,
        -2.0 * cosW0 / a0n,
        (1.0 - alpha) / a0n,
    )

    def process(x: float) -> float:
        return notch.process(lpf.process(hpf.process(x)))

    return process


# ─── TGAM byte-stream state-machine parser ───────────────────────────────────

class TGAMParser:
    """
    Stateful TGAM framing parser.

    Feed individual bytes via `feed(byte)`.  For each validated packet the
    `on_packet` callback receives the raw payload bytes as a list[int].
    Use `TGAMParser.parse_payload()` to decode a validated payload.
    """

    def __init__(self, on_packet: Callable[[List[int]], None]) -> None:
        self._on_packet = on_packet
        self._state: str = "SYNC1"
        self._payload_len: int = 0
        self._payload: List[int] = []

    def feed(self, byte: int) -> None:
        if self._state == "SYNC1":
            if byte == 0xAA:
                self._state = "SYNC2"

        elif self._state == "SYNC2":
            self._state = "LENGTH" if byte == 0xAA else "SYNC1"

        elif self._state == "LENGTH":
            if byte == 0xAA:
                return  # still syncing
            self._payload_len = byte
            self._payload = []
            self._state = "CHECKSUM" if self._payload_len == 0 else "PAYLOAD"

        elif self._state == "PAYLOAD":
            self._payload.append(byte)
            if len(self._payload) == self._payload_len:
                self._state = "CHECKSUM"

        elif self._state == "CHECKSUM":
            expected = (~(sum(self._payload) & 0xFF)) & 0xFF
            if expected == byte:
                self._on_packet(list(self._payload))
            self._state = "SYNC1"

    @staticmethod
    def parse_payload(payload: List[int]) -> Dict:
        """
        Decode a validated TGAM payload into a dict with named fields.

        Possible keys in the returned dict:
          raw         int    filtered raw ADC sample (int16)
          poorSignal  int    0–200
          attention   int    0–100
          meditation  int    0–100
          bandPower   dict   {delta, theta, lowAlpha, highAlpha,
                               lowBeta, highBeta, lowGamma, midGamma}
          battery     int    0–100
          version     str    firmware version string
        """
        result: Dict = {}
        i = 0
        while i < len(payload):
            code = payload[i]
            i += 1

            if code >= 0x80:
                # Extended code — next byte is payload length
                if i >= len(payload):
                    break
                length = payload[i]
                i += 1
                if i + length > len(payload):
                    break

                if code == CODE_RAW_EEG and length == 2:
                    raw = (payload[i] << 8) | payload[i + 1]
                    if raw > 32767:
                        raw -= 65536
                    result["raw"] = raw

                elif code == CODE_EEG_POWER and length == 24:
                    bp: Dict[str, int] = {}
                    for b, name in enumerate(BAND_NAMES):
                        bp[name] = (
                            (payload[i + b * 3]     << 16) |
                            (payload[i + b * 3 + 1] <<  8) |
                             payload[i + b * 3 + 2]
                        )
                    result["bandPower"] = bp

                elif code == CODE_EXTENDED and length >= 1:
                    result["battery"] = payload[i]
                    if length >= 3:
                        result["version"] = f"{payload[i + 1]}.{payload[i + 2]}"

                i += length

            else:
                # Single-byte value codes
                if code == CODE_POOR_SIGNAL:
                    result["poorSignal"] = payload[i]; i += 1
                elif code == CODE_ATTENTION:
                    result["attention"] = payload[i]; i += 1
                elif code == CODE_MEDITATION:
                    result["meditation"] = payload[i]; i += 1
                else:
                    i += 1  # unknown single-byte code — skip value byte

        return result
