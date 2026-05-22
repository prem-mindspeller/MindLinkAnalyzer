import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import serial
import serial.tools.list_ports
from cushy_serial import CushySerial

from .config import FocusCubeConfig
from .features import AdaptiveNormalizer, build_payload, compute_band_features


@dataclass(frozen=True)
class ExtendedEEGData:
    battery: int | None = None
    version: str | None = None


class PureTGAMBrainLinkParser:
    def __init__(self, on_raw, on_extend) -> None:
        self.on_raw = on_raw
        self.on_extend = on_extend
        self._state = "SYNC1"
        self._payload_len = 0
        self._payload: list[int] = []

    def parse(self, data: bytes) -> None:
        for byte in data:
            self.feed(byte)

    def feed(self, byte: int) -> None:
        if self._state == "SYNC1":
            if byte == 0xAA:
                self._state = "SYNC2"
        elif self._state == "SYNC2":
            self._state = "LENGTH" if byte == 0xAA else "SYNC1"
        elif self._state == "LENGTH":
            if byte == 0xAA:
                return
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
                self._parse_payload(self._payload)
            self._state = "SYNC1"

    def _parse_payload(self, payload: list[int]) -> None:
        i = 0
        while i < len(payload):
            code = payload[i]
            i += 1

            if code >= 0x80:
                if i >= len(payload):
                    break
                length = payload[i]
                i += 1
                if i + length > len(payload):
                    break

                if code == 0x80 and length == 2:
                    raw = (payload[i] << 8) | payload[i + 1]
                    if raw > 32767:
                        raw -= 65536
                    self.on_raw(raw)
                elif code == 0x85 and length >= 1:
                    version = None
                    if length >= 3:
                        version = f"{payload[i + 1]}.{payload[i + 2]}"
                    self.on_extend(ExtendedEEGData(battery=payload[i], version=version))

                i += length
            else:
                if i < len(payload):
                    i += 1


class BrainLinkRawSource:
    def __init__(
        self,
        config: FocusCubeConfig,
        port: str | None = None,
        allow_pure_parser: bool = False,
    ) -> None:
        self.config = config
        self.port = port
        self.allow_pure_parser = allow_pure_parser
        self.raw_samples: deque[float] = deque(maxlen=config.sample_rate * 8)
        self.normalizer = AdaptiveNormalizer(config.normalizer_window)
        self.battery: int | None = None
        self.firmware_version: str | None = None
        self._serial = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._open_event = threading.Event()
        self._open_error: Exception | None = None

    def start(self) -> None:
        port = self.port or detect_brainlink_port()
        if not port:
            raise RuntimeError("No BrainLink serial port found")

        self.port = port
        self._serial = CushySerial(port, self.config.serial_baud)
        parser = create_parser(
            self._on_raw,
            self._on_extend,
            allow_pure_parser=self.allow_pure_parser,
        )

        @self._serial.on_message()
        def handle_serial_message(msg: bytes) -> None:
            parser.parse(msg)

        def run() -> None:
            try:
                self._serial.open()
                self._open_event.set()
                while not self._stop.is_set():
                    time.sleep(0.1)
            except Exception as exc:
                self._open_error = exc
                self._open_event.set()
                print(
                    f"[FocusCube] BrainLink serial thread error on {port}: {exc}",
                    flush=True,
                )
            finally:
                if self._serial and getattr(self._serial, "is_open", False):
                    self._serial.close()

        self._thread = threading.Thread(target=run, name="brainlink-raw-source", daemon=True)
        self._thread.start()
        if not self._open_event.wait(timeout=5):
            raise RuntimeError(f"Timed out opening BrainLink serial port {port}")
        if self._open_error:
            raise RuntimeError(
                f"Could not open BrainLink serial port {port}: {self._open_error}. "
                "Close other apps that may use the headset, toggle Bluetooth off/on, "
                "or rerun with --list-ports and --serial-port COMx to choose another Bluetooth endpoint."
            ) from self._open_error

    def stop(self) -> None:
        self._stop.set()
        if self._serial and getattr(self._serial, "is_open", False):
            self._serial.close()
        if self._thread:
            self._thread.join(timeout=2)

    def payload(self) -> dict | None:
        if len(self.raw_samples) < self.config.window_size:
            return None
        features = compute_band_features(list(self.raw_samples), self.config)
        return build_payload(
            features,
            self.normalizer,
            self.config,
            mode="device",
            device_status=self.device_status,
        )

    @property
    def sample_count(self) -> int:
        return len(self.raw_samples)

    @property
    def device_status(self) -> dict:
        return {
            "connected": True,
            "port": self.port,
            "battery": self.battery,
            "firmwareVersion": self.firmware_version,
            "sampleCount": self.sample_count,
        }

    def _on_raw(self, raw) -> None:
        try:
            self.raw_samples.append(float(raw))
        except (TypeError, ValueError):
            return

    def _on_extend(self, data) -> None:
        self.battery = getattr(data, "battery", self.battery)
        self.firmware_version = getattr(data, "version", self.firmware_version)


def create_parser(on_raw, on_extend, allow_pure_parser: bool = False):
    repo_root = Path(__file__).resolve().parents[3]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    try:
        from BrainLinkParser.BrainLinkParser import BrainLinkParser
    except ImportError as exc:
        if not allow_pure_parser:
            raise ImportError(
                "Native BrainLinkParser.pyd could not be loaded. "
                "Use the Python environment that can import it, e.g. the repo's "
                "`brainlink` conda env, or rerun with --allow-pure-parser for "
                "protocol-only fallback."
            ) from exc
        print(
            "[FocusCube] Native BrainLinkParser unavailable; using pure-Python TGAM parser. "
            f"Reason: {exc}",
            flush=True,
        )
        return PureTGAMBrainLinkParser(on_raw=on_raw, on_extend=on_extend)

    def ignore_parser_attention(_data) -> None:
        return None

    def ignore_gyro(_x, _y, _z) -> None:
        return None

    def ignore_rr(_rr1, _rr2, _rr3) -> None:
        return None

    return BrainLinkParser(
        ignore_parser_attention,
        on_extend,
        ignore_gyro,
        ignore_rr,
        on_raw,
    )


def detect_brainlink_port() -> str | None:
    known_serials = (
        "5C361634682F",
        "5C3616327E59",
        "5C3616346938",
        "5C3616346838",
        "5C36163468D3",
        "5C3616327C21",
        "90E2FC2C5F37",
        "90E2FC2C627C",
        "90E2FC2C6378",
        "90E2FC2C5E7D",
        "90E2FC2C5FAA",
        "90E2FC2C614B",
    )
    keywords = ("brainlink", "neurosky", "ftdi", "silabs", "ch340")

    for port in serial.tools.list_ports.comports():
        hwid = getattr(port, "hwid", "") or ""
        description = (getattr(port, "description", "") or "").lower()
        device = getattr(port, "device", "") or ""

        if any(serial_id in hwid for serial_id in known_serials):
            return device
        if any(keyword in description for keyword in keywords):
            return device
        if device.startswith("/dev/tty.usbserial") or device.startswith("/dev/tty.usbmodem"):
            return device

    return None


def describe_ports() -> list[dict]:
    ports = []
    for port in serial.tools.list_ports.comports():
        ports.append(
            {
                "device": getattr(port, "device", "") or "",
                "description": getattr(port, "description", "") or "",
                "hwid": getattr(port, "hwid", "") or "",
                "manufacturer": getattr(port, "manufacturer", "") or "",
                "serialNumber": getattr(port, "serial_number", "") or "",
            }
        )
    return ports
