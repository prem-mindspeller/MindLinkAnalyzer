import asyncio
import json
import math
import os
import sys
import random
import threading
import time
import warnings
from collections import deque
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from scipy import stats as _scipy_stats
    from scipy.stats import chi2 as _scipy_chi2
    _SCIPY_AVAILABLE = True
except ImportError:
    _SCIPY_AVAILABLE = False

try:
    from scipy.signal.windows import dpss as _dpss
    _DPSS_AVAILABLE = True
except ImportError:
    _DPSS_AVAILABLE = False

try:
    import numpy as _np
    _NP_AVAILABLE = True
except ImportError:
    _NP_AVAILABLE = False

import serial
import serial.tools.list_ports
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

try:
    from cushy_serial import CushySerial as _CushySerial
    _HAVE_CUSHY_SERIAL = True
except Exception as _cushy_e:
    _CushySerial = None
    _HAVE_CUSHY_SERIAL = False

# Add workspace root to sys.path so BrainLinkParser package can be found
_WORKSPACE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, _WORKSPACE_ROOT)

# On Python 3.8+ (Windows) the DLL search path no longer includes the package
# directory automatically. Register the BrainLinkParser directory before import.
_BRAINLINK_PYD_DIR = os.path.join(_WORKSPACE_ROOT, "BrainLinkParser")
if hasattr(os, "add_dll_directory") and os.path.isdir(_BRAINLINK_PYD_DIR):
    try:
        os.add_dll_directory(_BRAINLINK_PYD_DIR)
    except Exception:
        pass

_USE_SDK = False
_BrainLinkParser = None
_SDK_IMPORT_ATTEMPTED = False


def _load_brainlink_parser():
    """Load the legacy BrainLink SDK only when the serial fallback path needs it."""
    global _USE_SDK, _BrainLinkParser, _SDK_IMPORT_ATTEMPTED
    if _SDK_IMPORT_ATTEMPTED:
        return _BrainLinkParser
    _SDK_IMPORT_ATTEMPTED = True
    try:
        from BrainLinkParser.BrainLinkParser import BrainLinkParser
        _BrainLinkParser = BrainLinkParser
        _USE_SDK = True
    except Exception:
        _BrainLinkParser = None
        _USE_SDK = False
    return _BrainLinkParser

from eeg_processor import TGAMParser, create_eeg_filter
from mindrove_device import (
    MINDROVE_CHANNEL_LABELS,
    MINDROVE_CHANNEL_ORDER,
    MINDROVE_SDK_AVAILABLE,
    MindRoveDevice,
)
from neuroprofile_traceability import (
    PROTOCOL_PROFILE_COMPONENTS,
    PROTOCOL_PROFILE_CONTRACT_VERSION,
    TASK_BASELINE_CONDITIONS,
    TASK_RECORDING_DURATIONS_SECONDS,
    build_neuroprofile_export,
    normalize_protocol_profile,
    normalize_protocol_validation_status,
    protocol_profile_reference,
    resolve_canonical_task,
    task_baseline_condition,
    theoretical_abilities_for_task,
)

# ─── Known BrainLink hardware identifiers ────────────────────────────────────
KNOWN_HWIDS  = ["5C361634682F", "5C3616327E59", "5C3616346938", "5C3616346838", "5C36163468D3", "5C3616327C21", "5C36163468D3", "90E2FC2C5F37", '90E2FC2C627C','90E2FC2C6378','90E2FC2C5E7D','90E2FC2C5FAA','90E2FC2C614B']
KNOWN_NAMES  = ["brainlink", "neurosky", "ftdi", "silabs", "ch340"]

# ─── Global connection state ──────────────────────────────────────────────────
_serial_port:   Optional[serial.Serial]   = None
_device_session: Optional[Any]            = None
_reader_thread: Optional[threading.Thread] = None
_active_connection_target: Optional[str]  = None
_stop_event:    threading.Event            = threading.Event()
_status:        str                        = "disconnected"
_battery_level: Optional[int]             = None    # last known battery % from 0x85 packet
_EEG_LOGS_ENABLED = os.getenv("EEG_DEBUG_LOGS", "1").strip().lower() not in ("0", "false", "no", "off")
_EEG_ANALYSIS_VERBOSE = os.getenv("EEG_ANALYSIS_VERBOSE", "0").strip().lower() in ("1", "true", "yes", "on")
# A channel with no data or near-zero variance carries no EEG (electrode off or
# disconnected). When at least half the channels are dead the headset reads as
# "not worn"; a present-but-artifacty signal reads as "noisy".
_MINDROVE_LIVE_FLATLINE_STD = float(os.getenv("MINDROVE_LIVE_FLATLINE_STD", "0.5") or "0.5")

# Asyncio queue bridging the serial-reader thread → WebSocket broadcaster
_broadcast_queue:  Optional[asyncio.Queue] = None
_broadcaster_task: Optional[asyncio.Task]  = None
_event_loop:       Optional[asyncio.AbstractEventLoop] = None

# Connected WebSocket clients
_ws_clients: Set[WebSocket] = set()


def _eeg_log(component: str, message: str, *, verbose: bool = False) -> None:
    if not _EEG_LOGS_ENABLED:
        return
    if verbose and not _EEG_ANALYSIS_VERBOSE:
        return
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] [MindLinkBackend] [{component}] {message}", flush=True)


def _raw_sample_shape(samples: List) -> str:
    if not samples:
        return "empty"
    counts = _raw_sample_kind_counts(samples)
    if counts["multichannel"]:
        keys: List[str] = []
        for sample in samples:
            if _is_multichannel_raw_sample(sample):
                source = sample.get("channels") if isinstance(sample, dict) and isinstance(sample.get("channels"), dict) else sample
                if isinstance(source, dict):
                    keys = sorted(
                        str(key)
                        for key in source.keys()
                        if str(key).lower().replace("_", "") in ("fp1", "fp2", "o1", "o2")
                    )
                else:
                    keys = list(MINDROVE_CHANNEL_ORDER)
                break
        if counts["multichannel"] != len(samples):
            return (
                f"mixed_raw mindrove={counts['multichannel']} scalar={counts['scalar']} "
                f"feature_dict={counts['feature_dict']} other={counts['other']} keys={keys}"
            )
        return f"mindrove_raw keys={keys}"
    first = samples[0]
    if isinstance(first, (int, float)):
        return "scalar_raw"
    if isinstance(first, dict):
        source = first.get("channels") if isinstance(first.get("channels"), dict) else first
        keys = sorted(str(key) for key in source.keys())
        channel_keys = [key for key in keys if key.lower().replace("_", "") in ("fp1", "fp2", "o1", "o2")]
        if channel_keys:
            return f"mindrove_raw keys={channel_keys}"
        return f"feature_dict keys={keys[:8]}{'...' if len(keys) > 8 else ''}"
    return type(first).__name__


def _mindrove_contact_state_from_samples(
    samples: List[Dict[str, Any]], fs: Optional[int] = None
) -> Dict[str, Any]:
    """Live signal state from a short multi-channel window.

    A channel is "dead" when it has no data or near-zero variance (electrode off
    or disconnected). When at least half the channels are dead the headset reads
    as "not worn" (poor_signal 200). Otherwise the worn signal is run through the
    same artifact QC used for recordings: a failing window reads as "noisy" (80)
    and a clean one as "good" (0). Per-channel reasons aid debugging.
    """
    if not samples or not _NP_AVAILABLE:
        return {
            "worn": False,
            "quality": 0.0,
            "reason": "no_samples",
            "poor_signal": 200,
            "channel_reasons": {},
        }

    sample_rate = int(fs or _RAW_EEG_FS)
    channel_reasons: Dict[str, str] = {}
    channel_values: Dict[str, List[float]] = {}
    for key in MINDROVE_CHANNEL_ORDER:
        values: List[float] = []
        for sample in samples:
            try:
                value = float(sample.get(key))
            except (TypeError, ValueError):
                continue
            if math.isfinite(value):
                values.append(value)
        if len(values) < 2:
            channel_reasons[key] = "missing"
        elif float(_np.std(values)) < _MINDROVE_LIVE_FLATLINE_STD:
            channel_reasons[key] = "flatline"
        else:
            channel_reasons[key] = ""
            channel_values[key] = values

    dead_channels = [key for key, reason in channel_reasons.items() if reason]
    channel_count = len(MINDROVE_CHANNEL_ORDER)
    dead_required = max(1, (channel_count + 1) // 2)
    quality = round(1.0 - (len(dead_channels) / channel_count), 3) if channel_count else 0.0
    if len(dead_channels) >= dead_required:
        return {
            "worn": False,
            "quality": quality,
            "reason": "signal_missing_or_flatline",
            "poor_signal": 200,
            "channel_reasons": channel_reasons,
            "dead_channels": dead_channels,
        }

    # Worn: aggregate the live channels and reuse the recording artifact QC so a
    # present-but-noisy signal still reads as noisy rather than clean.
    qc_reason = None
    if channel_values:
        length = min(len(values) for values in channel_values.values())
        aggregate = [
            sum(channel_values[key][index] for key in channel_values) / len(channel_values)
            for index in range(length)
        ]
        if len(aggregate) >= 2:
            qc_reason = _raw_window_qc(aggregate, fs=sample_rate)
    if qc_reason is not None:
        return {
            "worn": True,
            "quality": quality,
            "reason": qc_reason,
            "poor_signal": 80,
            "channel_reasons": channel_reasons,
            "dead_channels": dead_channels,
        }
    return {
        "worn": True,
        "quality": quality,
        "reason": "signal_good",
        "poor_signal": 0,
        "channel_reasons": channel_reasons,
        "dead_channels": dead_channels,
    }


class _MindRoveContactDebouncer:
    def __init__(self, good_required: int = 3, bad_required: int = 1):
        self.good_required = max(1, int(good_required))
        self.bad_required = max(1, int(bad_required))
        self._good_count = 0
        self._bad_count = 0
        self._current_worn = False
        self._last_state: Dict[str, Any] = {
            "worn": False,
            "quality": 0.0,
            "reason": "initial",
            "poor_signal": 200,
            "channel_reasons": {},
        }

    def update(self, state: Dict[str, Any]) -> Dict[str, Any]:
        if bool(state.get("worn")):
            self._good_count += 1
            self._bad_count = 0
            if self._good_count >= self.good_required:
                self._current_worn = True
        else:
            self._bad_count += 1
            self._good_count = 0
            if self._bad_count >= self.bad_required:
                self._current_worn = False

        smoothed = dict(state)
        smoothed["worn"] = self._current_worn
        if self._current_worn:
            smoothed["poor_signal"] = int(state.get("poor_signal", 0) or 0)
        else:
            smoothed["poor_signal"] = 200
            if bool(state.get("worn")):
                smoothed["reason"] = "debouncing_contact"
        self._last_state = smoothed
        return smoothed


# ─── WebSocket broadcast helpers ─────────────────────────────────────────────

async def _broadcast(message: dict) -> None:
    """Send a JSON message to every connected WebSocket client."""
    if not _ws_clients:
        return
    text = json.dumps(message)
    dead: Set[WebSocket] = set()
    for ws in list(_ws_clients):
        try:
            await ws.send_text(text)
        except Exception:
            dead.add(ws)
    _ws_clients.difference_update(dead)


async def _websocket_keepalive(ws: WebSocket, interval_seconds: float = 10.0) -> None:
    while True:
        try:
            await asyncio.wait_for(ws.receive_text(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            await ws.send_text(json.dumps({"type": "heartbeat", "ts": time.time()}))


async def _broadcaster() -> None:
    """
    Long-running task that drains _broadcast_queue and sends each message
    to all connected clients.  Runs inside the asyncio event loop.
    """
    assert _broadcast_queue is not None
    while True:
        try:
            msg = await asyncio.wait_for(_broadcast_queue.get(), timeout=1.0)
            await _broadcast(msg)
            _broadcast_queue.task_done()
        except asyncio.TimeoutError:
            pass
        except asyncio.CancelledError:
            break


# ─── Thread-safe queue helper (called from reader thread) ────────────────────

def _enqueue(message: dict) -> None:
    """Put a message into _broadcast_queue from the serial reader thread."""
    if _broadcast_queue is not None and _event_loop is not None:
        asyncio.run_coroutine_threadsafe(
            _broadcast_queue.put(message), _event_loop
        )


# ─── Serial reader (runs in a daemon thread) ──────────────────────────────────

def _mindrove_reader_worker() -> None:
    """
    Connect to a MindRove Wi-Fi device and broadcast FP1/FP2/O1/O2 samples.

    The frontend still receives a scalar raw stream for the oscilloscope, but
    recordings use the four-channel rawMulti stream.
    """
    global _device_session, _status, _active_connection_target

    device: Optional[MindRoveDevice] = None
    raw_batch: List[int] = []
    raw_multi_batch: List[Dict[str, int]] = []
    raw_multi_next_sample_index = 0
    signal_buffer = deque(maxlen=_live_signal_window_samples(_RAW_EEG_FS))
    signal_window_min = _raw_window_samples(_RAW_EEG_FS)
    contact_debouncer = _MindRoveContactDebouncer()
    filters: Dict[str, Any] = {}
    last_channel_rows: Tuple[int, ...] = ()
    last_flush = time.monotonic()
    last_quality = time.monotonic()
    last_data_time = time.monotonic()
    last_stream_log = time.monotonic()
    samples_since_log = 0
    FLUSH_INTERVAL = 0.016
    SILENCE_TIMEOUT = 5.0

    def _flush_raw_batches() -> None:
        nonlocal raw_batch, raw_multi_batch, raw_multi_next_sample_index, last_flush
        if raw_multi_batch:
            batch_size = len(raw_multi_batch)
            _enqueue({
                "type": "raw_multi_batch",
                "samples": list(raw_multi_batch),
                # WebSocket messages can queue while the renderer is busy.
                # This acquisition-clock index lets the frontend distinguish a
                # real missing batch from harmless browser delivery jitter.
                "streamStartSampleIndex": raw_multi_next_sample_index,
                "channels": [
                    {"key": key, "label": MINDROVE_CHANNEL_LABELS.get(key, key.upper())}
                    for key in MINDROVE_CHANNEL_ORDER
                ],
            })
            raw_multi_next_sample_index += batch_size
            raw_multi_batch.clear()
        if raw_batch:
            _enqueue({"type": "raw_batch", "samples": list(raw_batch)})
            raw_batch.clear()
        last_flush = time.monotonic()

    try:
        _eeg_log("MindRove", "reader starting")
        device = MindRoveDevice()
        _device_session = device
        _status = "connecting"
        _enqueue({"type": "status", "value": "connecting"})

        device.connect()
        fs = int(device.sample_rate or _RAW_EEG_FS)
        signal_window_min = _raw_window_samples(fs)
        signal_buffer = deque(maxlen=_live_signal_window_samples(fs))
        filters = {key: create_eeg_filter(fs=fs) for key in MINDROVE_CHANNEL_ORDER}
        last_channel_rows = tuple(ch.row_index for ch in device.channels)
        _eeg_log(
            "MindRove",
            f"connected fs={fs} rows={list(last_channel_rows)} channels={[ch.key for ch in device.channels]} "
            f"battery_channel={device.battery_channel}",
        )

        _status = "connected"
        _enqueue({"type": "status", "value": "connected"})
        _enqueue({
            "type": "device_info",
            "device": "mindrove",
            "sampleRate": fs,
            "channels": [
                {"key": ch.key, "label": ch.label, "row": ch.row_index}
                for ch in device.channels
            ],
        })

        while not _stop_event.is_set():
            samples = device.read_samples(max_samples=None)
            if samples:
                last_data_time = time.monotonic()
                samples_since_log += len(samples)
            if device.battery_level is not None:
                _set_battery_level(device.battery_level, "mindrove")

            current_channel_rows = tuple(ch.row_index for ch in device.channels)
            if current_channel_rows and current_channel_rows != last_channel_rows:
                _flush_raw_batches()
                filters = {key: create_eeg_filter(fs=fs) for key in MINDROVE_CHANNEL_ORDER}
                signal_buffer.clear()
                last_channel_rows = current_channel_rows
                # _eeg_log("MindRove", f"active_rows_updated rows={list(current_channel_rows)} filters_reset=true")
                _enqueue({
                    "type": "device_info",
                    "device": "mindrove",
                    "sampleRate": fs,
                    "channels": [
                        {"key": ch.key, "label": ch.label, "row": ch.row_index}
                        for ch in device.channels
                    ],
                })

            for sample in samples:
                filtered: Dict[str, int] = {}
                values: List[float] = []
                for key in MINDROVE_CHANNEL_ORDER:
                    if key not in sample:
                        continue
                    value = filters[key](float(sample[key]))
                    filtered[key] = int(round(value))
                    values.append(value)

                if not values:
                    continue

                aggregate = float(sum(values) / len(values))
                raw_multi_batch.append(filtered)
                raw_batch.append(int(round(aggregate)))
                signal_buffer.append(filtered)

            now = time.monotonic()
            if now - last_flush >= FLUSH_INTERVAL:
                _flush_raw_batches()

            if now - last_stream_log >= 1.0:
                # _eeg_log(
                #     "MindRoveStream",
                #     f"samples_last_sec={samples_since_log} rows={list(last_channel_rows)} "
                #     f"quality_buffer={len(quality_buffer)}/{quality_window} "
                #     f"battery={_battery_level if _battery_level is not None else 'n/a'} status={_status}",
                # )
                samples_since_log = 0
                last_stream_log = now

            if now - last_quality >= 1.0 and len(signal_buffer) >= signal_window_min:
                signal_state = _mindrove_contact_state_from_samples(list(signal_buffer), fs=fs)
                signal_state = contact_debouncer.update(signal_state)
                poor_signal = int(signal_state["poor_signal"])
                # _eeg_log(
                #     "MindRoveQC",
                #     f"worn={signal_state['worn']} reason={signal_state['reason']} "
                #     f"poor_signal={poor_signal} dead={signal_state.get('dead_channels', [])}",
                # )
                _enqueue({
                    "type": "eeg_data",
                    "poorSignal": poor_signal,
                    "attention": 0,
                    "meditation": 0,
                    "bandPower": None,
                    "battery": _battery_level,
                })
                last_quality = now

            if time.monotonic() - last_data_time > SILENCE_TIMEOUT:
                _eeg_log("MindRove", "device silent for 5 s; stopping reader")
                _enqueue({"type": "error", "message": "MindRove device silent for 5 s."})
                break

            if not samples:
                time.sleep(0.01)

        _flush_raw_batches()

    except Exception as exc:
        _eeg_log("MindRove", f"reader error: {exc}")
        _enqueue({"type": "error", "message": str(exc)})
    finally:
        if device is not None:
            try:
                device.disconnect()
            except Exception:
                pass
        _device_session = None
        _active_connection_target = None
        _status = "disconnected"
        _eeg_log("MindRove", "reader stopped")
        _enqueue({"type": "status", "value": "disconnected"})


def _reader_worker(port_path: str) -> None:
    """
    Opens the serial port, feeds bytes into the TGAM parser, batches raw
    samples (~60 fps) and forwards all parsed data to the broadcast queue.
    """
    global _serial_port, _status, _active_connection_target

    eeg_filter = create_eeg_filter()
    raw_batch: List[int] = []
    last_flush = time.monotonic()
    last_data_time = time.monotonic()
    FLUSH_INTERVAL = 0.016
    SILENCE_TIMEOUT = 3.0

    def _run_cushy_parser(parse_message) -> None:
        nonlocal last_data_time
        global _serial_port, _status

        serial_obj = None
        try:
            # CushySerial opens the port inside __init__ (pyserial behaviour);
            # do NOT call serial_obj.open() again — it would raise "Port is already open".
            serial_obj = _CushySerial(port_path, 115200)
            _serial_port = serial_obj

            @serial_obj.on_message()
            def handle_serial_message(msg: bytes):
                nonlocal last_data_time
                last_data_time = time.monotonic()
                parse_message(msg)

            _status = "connected"
            _enqueue({"type": "status", "value": "connected"})

            while not _stop_event.is_set():
                now = time.monotonic()
                if now - last_flush >= FLUSH_INTERVAL:
                    _flush_raw_batch()
                if now - last_data_time > SILENCE_TIMEOUT:
                    _enqueue({"type": "error", "message": "Device silent for 3 s — disconnecting."})
                    break
                time.sleep(0.02)

        except Exception as exc:
            print(f"[Backend] CushySerial error: {exc}", flush=True)
            _enqueue({"type": "error", "message": str(exc)})
        finally:
            if serial_obj and getattr(serial_obj, "is_open", False):
                try:
                    serial_obj.close()
                except Exception:
                    pass
            _serial_port = None
            _status = "disconnected"
            _enqueue({"type": "status", "value": "disconnected"})

    # ── Shared callbacks used by both SDK and fallback parser ────────────────
    def _flush_raw_batch():
        nonlocal raw_batch, last_flush
        if raw_batch:
            _enqueue({"type": "raw_batch", "samples": list(raw_batch)})
            raw_batch.clear()
            last_flush = time.monotonic()

    def _on_raw(raw):
        nonlocal last_data_time
        last_data_time = time.monotonic()
        raw_batch.append(round(eeg_filter(float(raw))))
        now = time.monotonic()
        if now - last_flush >= FLUSH_INTERVAL:
            _flush_raw_batch()

    def _on_eeg(data):
        nonlocal last_data_time
        last_data_time = time.monotonic()
        poor = getattr(data, 'poorSignal', getattr(data, 'signalLevel', getattr(data, 'signal', 200)))
        attn = getattr(data, 'attention',  0)
        med  = getattr(data, 'meditation', 0)
        _set_battery_level(_extract_battery_level(data), "sdk_eeg")
        # Band powers (attributes vary by firmware; use getattr with 0 default)
        bp_attrs = ['delta', 'theta', 'lowAlpha', 'highAlpha', 'lowBeta', 'highBeta', 'lowGamma', 'midGamma']
        bp = {k: getattr(data, k, 0) for k in bp_attrs}
        band_power = bp if any(bp.values()) else None
        _enqueue({
            "type":       "eeg_data",
            "poorSignal": poor,
            "attention":  attn,
            "meditation": med,
            "bandPower":  band_power,
            "battery":    _battery_level,
        })

    def _on_extend_eeg(data):
        battery_val = _extract_sdk_extend_battery(data)
        _set_battery_level(battery_val, "sdk_extend")

    def _noop(*args): pass

    # ── SDK parser path ──────────────────────────────────────────────────────
    BrainLinkParserClass = _load_brainlink_parser()
    if BrainLinkParserClass:
        sdk_parser = BrainLinkParserClass(_on_eeg, _on_extend_eeg, _noop, _noop, _on_raw)

        def _sdk_sidecar_on_packet(payload: List[int]) -> None:
            parsed = TGAMParser.parse_payload(payload)
            if "battery" not in parsed:
                return
            battery_val = _normalize_battery_level(parsed.get("battery"))
            _set_battery_level(battery_val, "sdk_sidecar_tgam")

        sdk_sidecar_parser = TGAMParser(_sdk_sidecar_on_packet)

        def _parse_sdk_chunk(chunk: bytes) -> None:
            sdk_parser.parse(chunk)
            for byte in chunk:
                sdk_sidecar_parser.feed(byte)

        if _HAVE_CUSHY_SERIAL:
            _run_cushy_parser(_parse_sdk_chunk)
            return

        try:
            _serial_port = serial.Serial(port_path, baudrate=115200, timeout=0.02)
            _status = "connected"
            _enqueue({"type": "status", "value": "connected"})

            while not _stop_event.is_set():
                chunk = _serial_port.read(64)
                if chunk:
                    last_data_time = time.monotonic()
                    _parse_sdk_chunk(chunk)

                now = time.monotonic()
                if now - last_flush >= FLUSH_INTERVAL:
                    _flush_raw_batch()

                if time.monotonic() - last_data_time > SILENCE_TIMEOUT:
                    _enqueue({"type": "error", "message": "Device silent for 3 s — disconnecting."})
                    break

        except (serial.SerialException, OSError) as exc:
            _enqueue({"type": "error", "message": str(exc)})
        finally:
            if _serial_port and _serial_port.is_open:
                try:
                    _serial_port.close()
                except Exception:
                    pass
            _serial_port = None
            _status = "disconnected"
            _enqueue({"type": "status", "value": "disconnected"})
        return   # SDK path handled; exit worker

    # ── Fallback: custom TGAM parser ─────────────────────────────────────────
    def on_packet(payload: List[int]) -> None:
        nonlocal raw_batch, last_flush
        data = TGAMParser.parse_payload(payload)

        if "raw" in data:
            raw_val = data["raw"]
            _enqueue({"type": "raw_unfiltered_batch", "samples": [raw_val]})
            raw_batch.append(round(eeg_filter(raw_val)))

        now = time.monotonic()
        if now - last_flush >= FLUSH_INTERVAL and raw_batch:
            _enqueue({"type": "raw_batch", "samples": list(raw_batch)})
            raw_batch.clear()
            last_flush = now

        if "battery" in data:
            raw_bat = data["battery"]
            print(f"[TGAM_0x85] raw battery byte={raw_bat}", flush=True)
            _set_battery_level(_normalize_battery_level(raw_bat), "tgam_extended")

        if "poorSignal" in data or "attention" in data:
            _enqueue({
                "type":       "eeg_data",
                "poorSignal": data.get("poorSignal", 200),
                "attention":  data.get("attention",  0),
                "meditation": data.get("meditation", 0),
                "bandPower":  data.get("bandPower"),
                "battery":    _battery_level,
            })

    tgam_parser = TGAMParser(on_packet)

    if _HAVE_CUSHY_SERIAL:
        _run_cushy_parser(lambda msg: [tgam_parser.feed(byte) for byte in msg])
        return

    try:
        _serial_port = serial.Serial(port_path, baudrate=115200, timeout=0.02)
        _status = "connected"
        _enqueue({"type": "status", "value": "connected"})

        while not _stop_event.is_set():
            chunk = _serial_port.read(64)

            if chunk:
                last_data_time = time.monotonic()
                for byte in chunk:
                    tgam_parser.feed(byte)

            now = time.monotonic()
            if now - last_flush >= FLUSH_INTERVAL and raw_batch:
                _enqueue({"type": "raw_batch", "samples": list(raw_batch)})
                raw_batch.clear()
                last_flush = now

            if time.monotonic() - last_data_time > SILENCE_TIMEOUT:
                _enqueue({"type": "error", "message": "Device silent for 3 s — disconnecting."})
                break

    except (serial.SerialException, OSError) as exc:
        _enqueue({"type": "error", "message": str(exc)})

    finally:
        if _serial_port and _serial_port.is_open:
            try:
                _serial_port.close()
            except Exception:
                pass
        _serial_port = None
        _active_connection_target = None
        _status = "disconnected"
        _enqueue({"type": "status", "value": "disconnected"})


# ─── Lifecycle ────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _broadcast_queue, _broadcaster_task, _event_loop
    _event_loop       = asyncio.get_running_loop()
    _broadcast_queue  = asyncio.Queue()
    _broadcaster_task = asyncio.create_task(_broadcaster())
    yield
    # Cleanup on shutdown
    if _broadcaster_task:
        _broadcaster_task.cancel()
    _stop_event.set()
    if _reader_thread and _reader_thread.is_alive():
        _reader_thread.join(timeout=2.0)




app = FastAPI(title="MindLink EEG Backend", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_methods=["*"],
    allow_headers=["*"],
)



@app.get("/health")
def health() -> Dict:
    """Readiness probe used by Electron to wait for backend startup."""
    return {"status": "ok"}


@app.get("/ports")
def list_ports() -> Dict:
    """Return available EEG devices with metadata."""
    mindrove_port = {
        "path": "mindrove://wifi",
        "pnpId": "MINDROVE_WIFI",
        "manufacturer": "MindRove",
        "description": "MindRove Wi-Fi EEG (FP1, FP2, O1, O2)",
        "deviceType": "mindrove",
        "available": MINDROVE_SDK_AVAILABLE,
        "channels": list(MINDROVE_CHANNEL_ORDER),
        "samplingRate": _RAW_EEG_FS,
    }
    try:
        import serial.tools.list_ports  # ensure platform module is loaded
        ports = [mindrove_port]
        for p in serial.tools.list_ports.comports():
            hwid = getattr(p, "hwid", "") or ""
            ports.append({
                "path":         p.device,
                "pnpId":        hwid,
                "manufacturer": p.manufacturer or "",
                "description":  p.description  or p.device,
                "deviceType":   "serial",
            })
        return {"ports": ports}
    except Exception:
        return {"ports": [mindrove_port]}



@app.get("/status")
def status() -> Dict:
    """Return current device connection status and last known battery level."""
    return {
        "status":  _status,
        "battery": _battery_level,
    }


@app.post("/connect")
def connect(body: Dict) -> Dict:
    """
    Open a connection to the configured EEG device.

    Request:  { "port": "mindrove://wifi" } or { "port": "COM3" }
    Response: { "success": true } | { "success": false, "error": "..." }
    """
    global _reader_thread, _status, _active_connection_target

    body = body or {}
    port_path = str(body.get("port", "mindrove://wifi")).strip()
    if not port_path:
        port_path = "mindrove://wifi"

    use_mindrove = port_path.startswith("mindrove://") or body.get("device") == "mindrove"
    connection_target = "mindrove://wifi" if use_mindrove else port_path
    _eeg_log("Connect", f"request target={connection_target} requested_port={port_path} status={_status}")

    if (
        _reader_thread
        and _reader_thread.is_alive()
        and _active_connection_target == connection_target
        and _status in ("connecting", "connected")
    ):
        _eeg_log("Connect", f"idempotent target={connection_target} status={_status}")
        # Re-broadcast the live status so a client that just set a local
        # "searching" state (e.g. a re-scan) recovers to it, instead of waiting
        # for a status change that never comes on an already-open connection.
        _enqueue({"type": "status", "value": _status})
        return {"success": True, "status": _status, "alreadyConnected": True}

    # Disconnect existing connection first
    _stop_event.set()
    if _reader_thread and _reader_thread.is_alive():
        _reader_thread.join(timeout=2.0)
        if _reader_thread.is_alive():
            _eeg_log("Connect", f"blocked target={connection_target}; existing reader still alive after join")
            return {
                "success": False,
                "error": "Existing EEG connection is still shutting down. Try again in a moment.",
            }
    _stop_event.clear()

    _status = "connecting"
    _enqueue({"type": "status", "value": "connecting"})

    target = _mindrove_reader_worker if use_mindrove else _reader_worker
    args = () if use_mindrove else (port_path,)
    _active_connection_target = connection_target

    _reader_thread = threading.Thread(
        target=target,
        args=args,
        daemon=True,
        name="eeg-reader",
    )
    _reader_thread.start()
    _eeg_log("Connect", f"reader_started target={connection_target} thread={_reader_thread.name}")

    return {"success": True}



@app.post("/disconnect")
def disconnect() -> Dict:
    """Close the active EEG device connection."""
    global _status, _device_session, _active_connection_target
    _eeg_log("Connect", f"disconnect request status={_status} target={_active_connection_target}")
    _stop_event.set()
    if _reader_thread and _reader_thread.is_alive():
        _reader_thread.join(timeout=2.0)
    if _device_session is not None:
        try:
            _device_session.disconnect()
        except Exception:
            pass
        _device_session = None
    _active_connection_target = None
    _stop_event.clear()
    _status = "disconnected"
    _enqueue({"type": "status", "value": "disconnected"})
    return {"success": True}


_BANDS = ["delta", "theta", "lowAlpha", "highAlpha", "lowBeta", "highBeta", "lowGamma", "midGamma"]

# Raw EEG conversion helpers used when the frontend sends raw MindRove samples
# instead of TGAM-chip band-power dicts.  Keep the 2 s analysis design, but
# derive sample counts from the device sample rate.
_RAW_EEG_FS      = 500    # MindRove default sample rate (Hz)
_LEGACY_RAW_EEG_FS = 512  # BrainLink scalar fallback sample rate (Hz)
_RAW_WINDOW_SECONDS = 2.0
# The live "Signal: Good/Noisy" indicator averages over a longer window than the
# 2 s analysis window so the displayed status does not flicker on brief noise.
_LIVE_SIGNAL_WINDOW_SECONDS = float(os.getenv("MINDROVE_LIVE_SIGNAL_WINDOW_SECONDS", "5.0") or "5.0")
_RAW_WINDOW_OVERLAP = 0.50
_RAW_WINDOW      = round(_RAW_WINDOW_SECONDS * _RAW_EEG_FS)
_RAW_STEP        = round(_RAW_WINDOW * (1.0 - _RAW_WINDOW_OVERLAP))
_MIN_CONTIGUOUS_CLEAN_SECONDS = 20.0
_MT_TAPERS       = 3      # DPSS multitaper count (matches legacy mt_tapers=3)
_MT_NW           = 2.5    # time-bandwidth product (matches legacy NW=2.5)
_INFERENTIAL_ABS_TOL = 1e-12
_INFERENTIAL_REL_TOL = 1e-9
_BATTERY_ATTRS = ("battery", "Battery", "electricity", "power")


def _raw_window_samples(fs: int = _RAW_EEG_FS) -> int:
    try:
        return max(1, int(round(_RAW_WINDOW_SECONDS * float(fs))))
    except Exception:
        return _RAW_WINDOW


def _live_signal_window_samples(fs: int = _RAW_EEG_FS) -> int:
    try:
        return max(1, int(round(_LIVE_SIGNAL_WINDOW_SECONDS * float(fs))))
    except Exception:
        return round(_LIVE_SIGNAL_WINDOW_SECONDS * _RAW_EEG_FS)


def _raw_step_samples(fs: int = _RAW_EEG_FS) -> int:
    return max(1, int(round(_raw_window_samples(fs) * (1.0 - _RAW_WINDOW_OVERLAP))))


def _empty_window_qc() -> Dict[str, Any]:
    return {
        "kept": 0,
        "rejected": 0,
        "not_worn": 0,
        "artifact": 0,
        "flatline": 0,
        "total_windows": 0,
        "max_contiguous_clean_windows": 0,
        "_current_contiguous_clean_windows": 0,
    }


def _record_window_qc(counters: Dict[str, Any], clean: bool, reason: Optional[str] = None) -> None:
    counters["total_windows"] += 1
    if clean:
        counters["kept"] += 1
        counters["_current_contiguous_clean_windows"] += 1
        counters["max_contiguous_clean_windows"] = max(
            counters["max_contiguous_clean_windows"],
            counters["_current_contiguous_clean_windows"],
        )
        return

    counters["rejected"] += 1
    counters["_current_contiguous_clean_windows"] = 0
    normalized_reason = reason if reason in {"not_worn", "artifact", "flatline"} else "artifact"
    counters[normalized_reason] += 1


def _finalize_window_qc(
    counters: Dict[str, Any],
    *,
    window_seconds: float = _RAW_WINDOW_SECONDS,
    step_seconds: Optional[float] = None,
) -> Dict[str, Any]:
    result = dict(counters)
    result.pop("_current_contiguous_clean_windows", None)
    step = float(step_seconds if step_seconds is not None else window_seconds * (1.0 - _RAW_WINDOW_OVERLAP))
    run = int(result.get("max_contiguous_clean_windows", 0) or 0)
    clean_seconds = 0.0 if run <= 0 else float(window_seconds + (run - 1) * step)
    result["window_seconds"] = float(window_seconds)
    result["window_overlap"] = float(_RAW_WINDOW_OVERLAP)
    result["step_seconds"] = step
    result["max_contiguous_clean_seconds"] = round(clean_seconds, 3)
    result["minimum_contiguous_clean_seconds"] = _MIN_CONTIGUOUS_CLEAN_SECONDS
    result["meets_contiguous_clean_minimum"] = clean_seconds >= _MIN_CONTIGUOUS_CLEAN_SECONDS
    return result


_MONTAGE_REGION_CHANNELS: Dict[str, tuple] = {
    "frontal": ("fp1", "fp2"),
    "occipital": ("o1", "o2"),
}
_MONTAGE_CHANNEL_INDEX = {
    key: idx for idx, key in enumerate(MINDROVE_CHANNEL_ORDER)
}
_MONTAGE_CHANNEL_DISPLAY = {
    "fp1": "Fp1",
    "fp2": "Fp2",
    "o1": "O1",
    "o2": "O2",
}
_MIN_PRIMARY_REGION_AGREEMENT = float(os.getenv("MINDROVE_MIN_PRIMARY_REGION_AGREEMENT", "0.15") or "0.15")

_OCCIPITAL_PRIMARY_TASKS = {
    "visuospatial_transformation_orientation",
    "rapid_visual_comparison",
    "pattern_closure_visual_noise",
}
_FRONTAL_PRIMARY_TASKS = {
    "adaptive_numerical_reasoning",
    "working_memory_manipulation",
    "auditory_target_counting",
    "semantic_induction_category_switching",
    "divergent_ideation",
    "dual_task_rule_switching",
    "speech_in_noise_comprehension",
}
_MIXED_REGION_TASKS = {
    "rule_based_anomaly_detection",
    "written_comprehension_synthesis",
}


def _debug_log(tag: str, message: str) -> None:
    _eeg_log(tag, message, verbose=True)


def _feature_sample(names: List[str], limit: int = 8) -> str:
    if not names:
        return "(none)"
    shown = names[:limit]
    suffix = "" if len(names) <= limit else f" ... (+{len(names) - limit} more)"
    return ", ".join(shown) + suffix


def _normalize_battery_level(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip().rstrip("%")
    try:
        level = int(float(value))
    except Exception:
        return None
    return max(0, min(100, level))


def _extract_battery_level(data: Any) -> Optional[int]:
    for attr in _BATTERY_ATTRS:
        level = _normalize_battery_level(getattr(data, attr, None))
        if level is not None:
            return level
    return None


def _extract_sdk_extend_battery(data: Any) -> Optional[int]:
    """Mirror the legacy GUI path: onExtendEEG reads `data.battery` directly."""
    return _normalize_battery_level(getattr(data, "battery", None))


def _set_battery_level(level: Optional[int], source: str = "") -> None:
    global _battery_level
    if level is None:
        return
    if level != _battery_level:
        _battery_level = level
        _eeg_log("Battery", f"level={_battery_level} source={source or 'unknown'}")
        _enqueue({"type": "battery", "level": _battery_level})

# TGAM frequency band ranges (Hz) for raw EEG conversion
_TGAM_BAND_HZ: Dict[str, tuple] = {
    "delta":     (1.0,   3.5),
    "theta":     (4.0,   7.5),
    "lowAlpha":  (7.5,   9.5),
    "highAlpha": (10.0,  12.0),
    "lowBeta":   (13.0,  17.0),
    "highBeta":  (18.0,  30.0),
    "lowGamma":  (31.0,  40.0),
    "midGamma":  (41.0,  50.0),
}

# TGAM gamma bands (suppressed when EMG guard fires)
_GAMMA_TGAM_BANDS = {"lowGamma", "midGamma"}


def _raw_to_bp_windows(raw_samples: List, fs: int = _RAW_EEG_FS) -> List[Dict]:
    """Convert a flat list of raw EEG integers to TGAM-style band-power dicts.

    VECTORISED: extracts all windows as a 2-D matrix and runs the FFT (and
    optional multitaper) on the entire batch in one numpy call.  EMG guard,
    SNR noise-floor subtraction, Shannon entropy, and peak descriptors are
    computed over the whole batch in numpy, then converted to the list-of-dicts
    format expected by the rest of the pipeline.
    """
    window_n = _raw_window_samples(fs)
    step_n = _raw_step_samples(fs)
    if not _NP_AVAILABLE or len(raw_samples) < window_n:
        return []

    arr    = _np.asarray(raw_samples, dtype=_np.float64)
    n      = len(arr)
    freqs  = _np.fft.rfftfreq(window_n, d=1.0 / fs)   # (n_freqs,)

    # ── Build strided window matrix without copying data where possible ───────
    n_win = max(0, (n - window_n) // step_n + 1)
    if n_win == 0:
        return []
    idx        = (_np.arange(n_win)[:, None] * step_n +
                  _np.arange(window_n)[None, :])       # (n_win, window_n)
    segs       = arr[idx]                                  # (n_win, window_n)
    segs       = segs - segs.mean(axis=1, keepdims=True)  # DC removal per window

    # ── Multitaper PSD (all windows, all tapers in one batch FFT) ─────────────
    hann   = _np.hanning(window_n)                       # fallback taper
    psd_batch = None                                       # (n_win, n_freqs)

    if _DPSS_AVAILABLE:
        try:
            tapers = _dpss(window_n, NW=_MT_NW, Kmax=_MT_TAPERS, sym=False)
            # tapers: (K, window_n)
            for k in range(_MT_TAPERS):
                tapered = segs * tapers[k]                # (n_win, window_n)
                Xk = _np.fft.rfft(tapered, axis=1)       # (n_win, n_freqs)
                Pk = (_np.abs(Xk) ** 2) / (fs * window_n + 1e-12)
                psd_batch = Pk if psd_batch is None else psd_batch + Pk
            psd_batch = psd_batch / float(_MT_TAPERS)
        except Exception:
            psd_batch = None

    if psd_batch is None:
        tapered   = segs * hann                           # (n_win, _RAW_WINDOW)
        Xk        = _np.fft.rfft(tapered, axis=1)        # (n_win, n_freqs)
        psd_batch = (_np.abs(Xk) ** 2) / (window_n * fs + 1e-12)

    # ── SNR noise-floor subtraction per window ─────────────────────────────────
    noise_floor = _np.percentile(psd_batch, 10, axis=1, keepdims=True)  # (n_win,1)
    snr_batch   = _np.maximum(psd_batch - noise_floor, 0.0)              # (n_win, n_freqs)

    # ── EMG guard per window: spectral slope 20–45 Hz + HF/mid ratio ─────────
    hf_mask  = (freqs >= 35) & (freqs <= 45)
    mid_mask = (freqs >= 20) & (freqs <= 30)
    use_mask = (freqs >= 20) & (freqs <= 45)
    emg_flags = _np.zeros(n_win, dtype=bool)
    if _np.any(hf_mask) and _np.any(mid_mask):
        hf_pwr  = psd_batch[:, hf_mask].sum(axis=1)   # (n_win,)
        mid_pwr = psd_batch[:, mid_mask].sum(axis=1)
        ratio_hf_mid = hf_pwr / (mid_pwr + 1e-12)
        f_sel = freqs[use_mask]
        if f_sel.size >= 3:
            logf = _np.log(f_sel + 1e-12)              # (n_use,)
            logp = _np.log(psd_batch[:, use_mask] + 1e-18)  # (n_win, n_use)
            # Vectorised OLS slope: slope = (n·Σ(logf·logp) - Σlogf·Σlogp) / (n·Σlogf² - (Σlogf)²)
            n_f  = float(f_sel.size)
            sf   = float(logf.sum())
            sf2  = float((logf ** 2).sum())
            denom_ols = n_f * sf2 - sf ** 2
            if abs(denom_ols) > 1e-12:
                sp  = logp.sum(axis=1)                 # (n_win,)
                sfp = (logp * logf).sum(axis=1)        # (n_win,)
                slopes = (n_f * sfp - sf * sp) / denom_ols
                emg_flags = (ratio_hf_mid > 1.2) | (slopes > -0.6)
            else:
                emg_flags = ratio_hf_mid > 1.2
        else:
            emg_flags = _np.ones(n_win, dtype=bool)

    # ── Assemble list of dicts (band-level ops remain per-band, not per-window) ─
    # Pre-compute freq masks for all bands
    band_items  = list(_TGAM_BAND_HZ.items())
    band_masks  = {band: (freqs >= flo) & (freqs < fhi)
                   for band, (flo, fhi) in band_items}

    result: List[Dict] = []
    for wi in range(n_win):
        psd     = psd_batch[wi]     # (n_freqs,)
        snr_psd = snr_batch[wi]
        emg     = bool(emg_flags[wi])
        bp: Dict[str, Any] = {"_emg_guard": 1 if emg else 0}

        for band, (flo, fhi) in band_items:
            mask         = band_masks[band]
            raw_band_psd = psd[mask]
            snr_band_psd = snr_psd[mask]

            if emg and band in _GAMMA_TGAM_BANDS:
                bp[band]                = 0.0
                bp[f"{band}_peak_freq"] = (flo + fhi) / 2.0
                bp[f"{band}_peak_amp"]  = 0.0
                bp[f"{band}_entropy"]   = 0.0
                continue

            bp[band] = float(snr_band_psd.sum() * 1e12) if snr_band_psd.size else 0.0

            if raw_band_psd.size:
                pk_idx                  = int(raw_band_psd.argmax())
                bp[f"{band}_peak_freq"] = float(freqs[mask][pk_idx])
                bp[f"{band}_peak_amp"]  = float(raw_band_psd[pk_idx] * 1e12)
            else:
                bp[f"{band}_peak_freq"] = (flo + fhi) / 2.0
                bp[f"{band}_peak_amp"]  = 0.0

            s = snr_band_psd.sum()
            if snr_band_psd.size > 0 and s > 1e-24:
                p_bins = snr_band_psd / (s + 1e-12)
                p_bins = p_bins / (p_bins.sum() + 1e-12)
                p_bins = _np.clip(p_bins, 1e-12, 1.0)
                bp[f"{band}_entropy"] = float(-(p_bins * _np.log2(p_bins)).sum())
            else:
                bp[f"{band}_entropy"] = 0.0

        result.append(bp)
    return result


_RAW_FEATURE_BANDS: Dict[str, tuple] = {
    "delta":  (0.5,  4.0),
    "theta":  (4.0,  8.0),
    "alpha":  (8.0, 13.0),
    "beta":   (13.0, 30.0),
    "gamma":  (30.0, 45.0),
    "theta1": (4.0,  6.0),
    "theta2": (6.0,  8.0),
    "beta1":  (13.0, 20.0),
    "beta2":  (20.0, 30.0),
}


def _trapz(y, x=None) -> float:
    if not _NP_AVAILABLE:
        return 0.0
    try:
        return float(_np.trapezoid(y, x))
    except AttributeError:
        return float(_np.trapz(y, x))


def _iter_raw_windows(raw_samples: List, fs: int = _RAW_EEG_FS) -> List:
    window_n = _raw_window_samples(fs)
    step_n = _raw_step_samples(fs)
    if not _NP_AVAILABLE or len(raw_samples) < window_n:
        return []
    arr = _np.asarray(raw_samples, dtype=_np.float64)
    windows = []
    for start in range(0, len(arr) - window_n + 1, step_n):
        windows.append(arr[start:start + window_n])
    return windows


def _window_psd(window, fs: int = _RAW_EEG_FS):
    x = _np.asarray(window, dtype=_np.float64)
    x = x - _np.mean(x)
    psd = None
    freqs = _np.fft.rfftfreq(x.size, d=1.0 / fs)

    if _DPSS_AVAILABLE:
        try:
            tapers = _dpss(x.size, NW=_MT_NW, Kmax=max(1, int(_MT_TAPERS)), sym=False)
            psd_accum = None
            for taper in tapers:
                Xk = _np.fft.rfft(x * taper)
                Pk = (_np.abs(Xk) ** 2) / (fs * x.size + 1e-12)
                psd_accum = Pk if psd_accum is None else psd_accum + Pk
            psd = psd_accum / float(len(tapers))
        except Exception:
            psd = None

    if psd is None:
        tapered = x * _np.hanning(x.size)
        Xk = _np.fft.rfft(tapered)
        psd = (_np.abs(Xk) ** 2) / (fs * x.size + 1e-12)

    return freqs, psd, x


def _raw_window_qc(window, fs: int = _RAW_EEG_FS) -> Optional[str]:
    if not _NP_AVAILABLE:
        return None
    x = _np.asarray(window, dtype=_np.float64)
    med = float(_np.median(x))
    mad = float(_np.median(_np.abs(x - med))) + 1e-12
    scale = 1.4826 * mad

    if scale < 0.5:
        return "flatline"

    try:
        freqs, psd, _ = _window_psd(x, fs)
        total = float(_np.sum(psd)) + 1e-12
        neural_ratio = float(_np.sum(psd[(freqs >= 0.5) & (freqs <= 30.0)])) / total
        hf_ratio = float(_np.sum(psd[freqs >= 35.0])) / total
        valid = (freqs >= 1.0) & (freqs <= 40.0) & (psd > 0)
        if int(_np.sum(valid)) > 10:
            slope, _ = _np.polyfit(_np.log10(freqs[valid]), _np.log10(psd[valid]), 1)
        else:
            slope = -1.0
        hf_threshold = 0.70 if slope < -0.5 else 0.50
        if neural_ratio < 0.20 or slope > -0.1 or hf_ratio > hf_threshold:
            return "not_worn"
    except Exception:
        if scale > 400.0:
            return "not_worn"

    extreme_outliers = _np.abs(x - med) > (20.0 * scale)
    if int(_np.sum(extreme_outliers)) > (len(x) * 0.05) and scale > 10.0:
        return "artifact"

    return None


def _raw_window_to_features(window, fs: int = _RAW_EEG_FS) -> Dict[str, float]:
    freqs, psd, x = _window_psd(window, fs)
    noise_floor = float(_np.percentile(psd, 10)) if psd.size else 0.0
    snr_psd = _np.maximum(psd - noise_floor, 0.0)
    psd_norm = (psd - max(noise_floor, 1e-12)) / max(noise_floor, 1e-12)
    total_power = float(_np.var(x))
    total_snr = _trapz(snr_psd, freqs) if psd.size else 0.0
    denom = total_snr if total_snr > 0 else total_power + 1e-12

    features: Dict[str, float] = {}
    band_powers: Dict[str, float] = {}

    for band_name, (low, high) in _RAW_FEATURE_BANDS.items():
        mask = (freqs >= low) & (freqs <= high)
        if not _np.any(mask):
            mid = (low + high) / 2.0
            features[f"{band_name}_power"] = 0.0
            features[f"{band_name}_power_raw"] = 0.0
            features[f"{band_name}_relative"] = 0.0
            features[f"{band_name}_peak_freq"] = mid
            features[f"{band_name}_peak_amp"] = 0.0
            features[f"{band_name}_peak_rel_amp"] = 0.0
            features[f"{band_name}_entropy"] = 0.0
            band_powers[band_name] = 0.0
            continue

        band_freqs = freqs[mask]
        band_psd = psd[mask]
        band_snr = snr_psd[mask]
        band_norm = psd_norm[mask]
        raw_power = _trapz(band_psd, band_freqs)
        snr_power = _trapz(band_snr, band_freqs)
        band_powers[band_name] = snr_power
        features[f"{band_name}_power"] = snr_power
        features[f"{band_name}_power_raw"] = raw_power
        features[f"{band_name}_relative"] = snr_power / (denom + 1e-12)

        peak_idx = int(_np.argmax(band_norm))
        peak_amp_norm = float(band_norm[peak_idx])
        mean_band = float(_np.mean(band_norm)) + 1e-12
        features[f"{band_name}_peak_freq"] = float(band_freqs[peak_idx])
        features[f"{band_name}_peak_amp"] = float(band_psd[peak_idx])
        features[f"{band_name}_peak_rel_amp"] = peak_amp_norm / mean_band

        p = band_norm / (float(_np.sum(band_norm)) + 1e-12)
        p = _np.clip(p, 1e-12, 1.0)
        p = p / (float(_np.sum(p)) + 1e-12)
        features[f"{band_name}_entropy"] = float(-_np.sum(p * _np.log2(p)))

    emg_flag = False
    try:
        hf_mask = (freqs >= 35.0) & (freqs <= 45.0)
        mid_mask = (freqs >= 20.0) & (freqs <= 30.0)
        hf_power = _trapz(psd[hf_mask], freqs[hf_mask]) if _np.any(hf_mask) else 0.0
        mid_power = _trapz(psd[mid_mask], freqs[mid_mask]) if _np.any(mid_mask) else 0.0
        ratio_hf_mid = hf_power / (mid_power + 1e-12)
        use_mask = (freqs >= 20.0) & (freqs <= 45.0)
        f_sel = freqs[use_mask]
        p_sel = psd[use_mask]
        if f_sel.size >= 3:
            logf = _np.log(f_sel + 1e-12)
            logp = _np.log(p_sel + 1e-18)
            A = _np.vstack([logf, _np.ones_like(logf)]).T
            slope, _ = _np.linalg.lstsq(A, logp, rcond=None)[0]
            emg_flag = bool(ratio_hf_mid > 1.2 or slope > -0.6)
        else:
            emg_flag = True
    except Exception:
        emg_flag = False

    if emg_flag:
        for suffix in ("power", "power_raw", "relative", "peak_freq", "peak_amp", "peak_rel_amp", "entropy"):
            features[f"gamma_{suffix}"] = 0.0

    features["_emg_guard"] = float(1 if emg_flag else 0)
    features["_gamma_evaluated"] = float(0 if emg_flag else 1)
    features["alpha_theta_ratio"] = band_powers.get("alpha", 0.0) / (band_powers.get("theta", 0.0) + 1e-10)
    features["beta_alpha_ratio"] = band_powers.get("beta", 0.0) / (band_powers.get("alpha", 0.0) + 1e-10)
    features["beta2_beta1_ratio"] = band_powers.get("beta2", 0.0) / (band_powers.get("beta1", 0.0) + 1e-10)
    features["theta2_theta1_ratio"] = band_powers.get("theta2", 0.0) / (band_powers.get("theta1", 0.0) + 1e-10)
    features["total_power"] = total_power
    return features


def _normalize_raw_channel_key(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "").replace("_", "")


def _sample_channel_map(sample: Any) -> Optional[Dict[str, Any]]:
    if isinstance(sample, dict):
        source = sample.get("channels") if isinstance(sample.get("channels"), dict) else sample
        return {_normalize_raw_channel_key(k): v for k, v in source.items()}
    if isinstance(sample, (list, tuple)) and len(sample) >= len(MINDROVE_CHANNEL_ORDER):
        return {
            key: sample[idx]
            for idx, key in enumerate(MINDROVE_CHANNEL_ORDER)
        }
    return None


def _has_multichannel_raw_shape(sample: Any) -> bool:
    channel_map = _sample_channel_map(sample)
    if not channel_map:
        return False
    return all(key in channel_map for key in MINDROVE_CHANNEL_ORDER)


def _is_multichannel_raw_sample(sample: Any) -> bool:
    if not _has_multichannel_raw_shape(sample):
        return False
    channel_map = _sample_channel_map(sample) or {}
    try:
        return all(math.isfinite(float(channel_map[key])) for key in MINDROVE_CHANNEL_ORDER)
    except (TypeError, ValueError, OverflowError):
        return False


def _raw_sample_kind_counts(samples: List) -> Dict[str, int]:
    counts = {
        "multichannel": 0,
        "scalar": 0,
        "feature_dict": 0,
        "other": 0,
    }
    for sample in samples or []:
        if _is_multichannel_raw_sample(sample):
            counts["multichannel"] += 1
        elif isinstance(sample, (int, float)):
            counts["scalar"] += 1
        elif isinstance(sample, dict):
            counts["feature_dict"] += 1
        else:
            counts["other"] += 1
    return counts


def _multichannel_raw_subset(samples: List) -> List:
    return [sample for sample in samples or [] if _is_multichannel_raw_sample(sample)]


def _scalar_raw_subset(samples: List) -> List:
    return [sample for sample in samples or [] if isinstance(sample, (int, float))]


def _feature_dict_subset(samples: List) -> List[Dict]:
    return [
        sample for sample in samples or []
        if isinstance(sample, dict) and not _has_multichannel_raw_shape(sample)
    ]


def _contiguous_sample_runs(samples: List, predicate) -> List[List[Any]]:
    """Return consecutive runs without stitching across other sample types."""
    return [run for _, run in _contiguous_sample_runs_with_offsets(samples, predicate)]


def _contiguous_sample_runs_with_offsets(samples: List, predicate) -> List[Tuple[int, List[Any]]]:
    """Return ``(start_index, run)`` pairs without crossing invalid sample gaps."""
    runs: List[Tuple[int, List[Any]]] = []
    current: List[Any] = []
    current_start = 0
    for index, sample in enumerate(samples or []):
        if predicate(sample):
            if not current:
                current_start = index
            current.append(sample)
        elif current:
            runs.append((current_start, current))
            current = []
    if current:
        runs.append((current_start, current))
    return runs


def _coerce_sample_index(value: Any) -> Optional[int]:
    """Parse a finite, integer-valued sample index without silently truncating."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or not number.is_integer():
        return None
    return int(number)


def _transport_segments_from_metadata(
    metadata: Any,
    sample_count: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Validate transport-run boundaries and return safe, non-overlapping slices.

    Segment ends are exclusive and refer to positions in the submitted sample
    array.  Adjacent segments deliberately remain separate: a transport restart
    at the same array boundary must not create a synthetic continuous EEG run.
    Requests made before this sidecar existed retain the historical whole-array
    behaviour.
    """
    safe_count = max(0, int(sample_count or 0))
    metadata_dict = metadata if isinstance(metadata, dict) else {}
    recording = metadata_dict.get("recording")
    recording_dict = recording if isinstance(recording, dict) else {}
    raw_segments = recording_dict.get("transport_segments")
    if raw_segments is None:
        raw_segments = metadata_dict.get("transport_segments")

    provided = raw_segments is not None
    input_segments = raw_segments if isinstance(raw_segments, list) else []
    candidates: List[Tuple[int, int, int, bool, Optional[float], Optional[float]]] = []
    rejected = 0
    adjusted = 0

    for input_index, segment in enumerate(input_segments):
        if not isinstance(segment, dict):
            rejected += 1
            continue
        start = _coerce_sample_index(segment.get("start_sample_index"))
        end = _coerce_sample_index(segment.get("end_sample_index_exclusive"))
        if start is None or end is None or end <= start:
            rejected += 1
            continue
        bounded_start = max(0, min(safe_count, start))
        bounded_end = max(0, min(safe_count, end))
        was_adjusted = bounded_start != start or bounded_end != end
        if bounded_end <= bounded_start:
            rejected += 1
            continue
        elapsed_values: List[Optional[float]] = []
        for elapsed_key in ("start_elapsed_ms", "end_elapsed_ms"):
            try:
                elapsed_value = float(segment.get(elapsed_key))
            except (TypeError, ValueError):
                elapsed_value = None
            if elapsed_value is not None and (
                not math.isfinite(elapsed_value) or elapsed_value < 0.0
            ):
                elapsed_value = None
            elapsed_values.append(elapsed_value)
        candidates.append((
            bounded_start,
            bounded_end,
            input_index,
            was_adjusted,
            elapsed_values[0],
            elapsed_values[1],
        ))

    candidates.sort(key=lambda item: (item[0], item[1], item[2]))
    normalized: List[Dict[str, Any]] = []
    previous_end = 0
    for start, end, _input_index, was_adjusted, start_elapsed_ms, end_elapsed_ms in candidates:
        if normalized and start < previous_end:
            start = previous_end
            was_adjusted = True
        if end <= start:
            rejected += 1
            continue
        if was_adjusted:
            adjusted += 1
        normalized_segment: Dict[str, Any] = {
            "segment_id": len(normalized),
            "start_sample_index": start,
            "end_sample_index_exclusive": end,
        }
        if start_elapsed_ms is not None:
            normalized_segment["start_elapsed_ms"] = start_elapsed_ms
        if end_elapsed_ms is not None:
            normalized_segment["end_elapsed_ms"] = end_elapsed_ms
        normalized.append(normalized_segment)
        previous_end = end

    fallback = False
    if not normalized and safe_count > 0 and not provided:
        normalized = [{
            "segment_id": 0,
            "start_sample_index": 0,
            "end_sample_index_exclusive": safe_count,
        }]

    return normalized, {
        "provided": bool(provided),
        "input_segment_count": len(input_segments),
        "analyzed_segment_count": len(normalized),
        "rejected_segment_count": int(rejected),
        "adjusted_segment_count": int(adjusted),
        "fallback_to_whole_array": bool(fallback),
        "metadata_invalidated_recording": bool(provided and safe_count > 0 and not normalized),
        "segments": [dict(segment) for segment in normalized],
    }


def _annotate_feature_window(
    row: Dict[str, float],
    *,
    segment_id: str,
    start_sample_index: int,
    end_sample_index_exclusive: int,
    start_seconds: float,
    end_seconds: float,
) -> None:
    """Attach transport/timing fields; underscore fields never enter inference."""
    row["_transport_segment_id"] = segment_id
    row["_window_start_sample_index"] = int(start_sample_index)
    row["_window_end_sample_index_exclusive"] = int(end_sample_index_exclusive)
    row["_window_start_seconds"] = float(start_seconds)
    row["_window_end_seconds"] = float(end_seconds)


def _log_mixed_sample_use(component: str, samples: List, using: str, *, task_id: str = "") -> None:
    counts = _raw_sample_kind_counts(samples)
    total = sum(counts.values())
    if total <= counts.get(using, 0):
        return
    task_part = f" task={task_id}" if task_id else ""
    _eeg_log(
        component,
        (
            f"mixed_sample_types{task_part} using={using} total={total} "
            f"mindrove={counts['multichannel']} scalar={counts['scalar']} "
            f"feature_dict={counts['feature_dict']} other={counts['other']}"
        ),
    )


def _coerce_multichannel_raw_samples(samples: List) -> Optional[Any]:
    if not _NP_AVAILABLE or not samples:
        return None

    rows = []
    for sample in _multichannel_raw_subset(samples):
        channel_map = _sample_channel_map(sample)
        if not channel_map:
            continue
        row = []
        valid = True
        for key in MINDROVE_CHANNEL_ORDER:
            try:
                value = float(channel_map[key])
            except Exception:
                valid = False
                break
            if not math.isfinite(value):
                valid = False
                break
            row.append(value)
        if valid:
            rows.append(row)

    if not rows:
        return None
    return _np.asarray(rows, dtype=_np.float64)


def _montage_profile_for_task(task_id: str = "") -> Dict[str, Any]:
    raw_tid = (task_id or "").lower()
    tid = resolve_canonical_task(raw_tid) or raw_tid
    if tid in _OCCIPITAL_PRIMARY_TASKS:
        return {
            "primary_region": "occipital",
            "secondary_region": "frontal",
            "region_weights": {"occipital": 0.80, "frontal": 0.20},
        }
    if tid in _FRONTAL_PRIMARY_TASKS:
        return {
            "primary_region": "frontal",
            "secondary_region": "occipital",
            "region_weights": {"frontal": 0.80, "occipital": 0.20},
        }
    if tid in _MIXED_REGION_TASKS:
        return {
            "primary_region": "frontal_occipital",
            "secondary_region": "balanced_context",
            "region_weights": {"frontal": 0.55, "occipital": 0.45},
        }
    return {
        "primary_region": "balanced",
        "secondary_region": "none",
        "region_weights": {"frontal": 0.50, "occipital": 0.50},
    }


def _combine_feature_rows_weighted(row_weight_pairs: List[tuple]) -> Dict[str, float]:
    row_weight_pairs = [
        (row, float(weight))
        for row, weight in row_weight_pairs
        if row and math.isfinite(float(weight)) and float(weight) > 0.0
    ]
    if not row_weight_pairs or not _NP_AVAILABLE:
        return {}

    out: Dict[str, float] = {}
    keys = set().union(*(row.keys() for row, _ in row_weight_pairs))
    for key in keys:
        weighted_values = []
        weights = []
        for row, weight in row_weight_pairs:
            if key not in row:
                continue
            try:
                value = float(row[key])
            except Exception:
                continue
            if math.isfinite(value):
                weighted_values.append(value * weight)
                weights.append(weight)
        if not weights:
            continue

        value = float(sum(weighted_values) / (sum(weights) + 1e-12))
        if key in ("_emg_guard", "_gamma_evaluated"):
            out[key] = float(1 if value >= 0.5 else 0)
        else:
            out[key] = value
    if out.get("_emg_guard", 0.0) >= 1.0:
        out["_gamma_evaluated"] = 0.0
    return out


def _safe_positive(value: Any, floor: float = 1e-12) -> float:
    try:
        value = float(value)
    except Exception:
        return floor
    if not math.isfinite(value):
        return floor
    return max(floor, value)


def _spatial_contrast_features(region_rows: Dict[str, Dict[str, float]]) -> Dict[str, float]:
    frontal = region_rows.get("frontal")
    occipital = region_rows.get("occipital")
    if not frontal or not occipital:
        return {}

    fp_alpha = _safe_positive(frontal.get("alpha_power"))
    o_alpha = _safe_positive(occipital.get("alpha_power"))
    fp_beta = _safe_positive(frontal.get("beta_power"))
    o_beta = _safe_positive(occipital.get("beta_power"))
    fp_beta_alpha = _safe_positive(frontal.get("beta_alpha_ratio"))
    o_beta_alpha = _safe_positive(occipital.get("beta_alpha_ratio"))
    return {
        "posterior_anterior_alpha": math.log(o_alpha) - math.log(fp_alpha),
        "posterior_anterior_beta": math.log(fp_beta) - math.log(o_beta),
        "occipital_alpha_advantage": o_alpha / fp_alpha,
        "frontal_attention_advantage": fp_beta_alpha / o_beta_alpha,
        "front_occipital_alpha_ratio": o_alpha / fp_alpha,
        "front_occipital_beta_ratio": fp_beta / o_beta,
    }


def _aggregate_channel_feature_rows(rows: List[Dict[str, float]]) -> Dict[str, float]:
    if not rows:
        return {}
    return _combine_feature_rows_weighted([(row, 1.0) for row in rows])


def _region_feature_rows(channel_rows: Dict[str, Dict[str, float]]) -> Dict[str, Dict[str, float]]:
    regions: Dict[str, Dict[str, float]] = {}
    for region, channels in _MONTAGE_REGION_CHANNELS.items():
        pairs = [
            (channel_rows[key], 1.0)
            for key in channels
            if key in channel_rows
        ]
        row = _combine_feature_rows_weighted(pairs)
        if row:
            regions[region] = row
    return regions


def _task_weighted_montage_features(
    channel_rows: Dict[str, Dict[str, float]],
    task_id: str = "",
) -> Dict[str, float]:
    region_rows = _region_feature_rows(channel_rows)
    profile = _montage_profile_for_task(task_id)
    pairs = []
    for region, weight in profile["region_weights"].items():
        if region in region_rows:
            pairs.append((region_rows[region], weight))
    if pairs:
        row = _combine_feature_rows_weighted(pairs)
    else:
        row = _aggregate_channel_feature_rows(list(channel_rows.values()))

    row.update(_spatial_contrast_features(region_rows))
    primary = profile["primary_region"]
    if primary in _MONTAGE_REGION_CHANNELS:
        primary_channels = _MONTAGE_REGION_CHANNELS[primary]
        present = [key for key in primary_channels if key in channel_rows]
        row["_primary_region_valid_channel_count"] = float(len(present))
        row["_primary_region_complete"] = float(1 if len(present) == len(primary_channels) else 0)
        row["_evidence_region_weight"] = float(profile["region_weights"].get(primary, 0.0))
        row["_evidence_region_code"] = float(1 if primary == "frontal" else 2 if primary == "occipital" else 0)
    elif primary == "frontal_occipital":
        frontal_count = sum(1 for key in _MONTAGE_REGION_CHANNELS["frontal"] if key in channel_rows)
        occ_count = sum(1 for key in _MONTAGE_REGION_CHANNELS["occipital"] if key in channel_rows)
        row["_primary_region_valid_channel_count"] = float(min(frontal_count, occ_count))
        row["_primary_region_complete"] = float(1 if frontal_count >= 1 and occ_count >= 1 else 0)
        row["_evidence_region_weight"] = 1.0
        row["_evidence_region_code"] = 3.0
    return row


def _missing_required_region_reason(channel_rows: Dict[str, Dict[str, float]], task_id: str = "") -> Optional[str]:
    profile = _montage_profile_for_task(task_id)
    primary = profile["primary_region"]
    if primary in ("frontal", "occipital"):
        if any(key in channel_rows for key in _MONTAGE_REGION_CHANNELS[primary]):
            return None
        return f"missing_{primary}_region"
    if primary == "frontal_occipital":
        frontal_ok = any(key in channel_rows for key in _MONTAGE_REGION_CHANNELS["frontal"])
        occipital_ok = any(key in channel_rows for key in _MONTAGE_REGION_CHANNELS["occipital"])
        if frontal_ok and occipital_ok:
            return None
        return "missing_mixed_regions"
    return None


def _regional_channel_agreements(window, channel_rows: Dict[str, Dict[str, float]]) -> Dict[str, Optional[float]]:
    agreements: Dict[str, Optional[float]] = {}
    if not _NP_AVAILABLE:
        return agreements
    try:
        arr = _np.asarray(window, dtype=_np.float64)
    except Exception:
        return agreements
    if arr.ndim != 2:
        return agreements

    for region, channels in _MONTAGE_REGION_CHANNELS.items():
        if not all(key in channel_rows for key in channels):
            agreements[region] = None
            continue
        try:
            a_idx = _MONTAGE_CHANNEL_INDEX[channels[0]]
            b_idx = _MONTAGE_CHANNEL_INDEX[channels[1]]
        except KeyError:
            agreements[region] = None
            continue
        if arr.shape[1] <= max(a_idx, b_idx):
            agreements[region] = None
            continue
        agreements[region] = _safe_corr(arr[:, a_idx], arr[:, b_idx])
    return agreements


def _low_primary_region_agreement(
    window,
    channel_rows: Dict[str, Dict[str, float]],
    task_id: str = "",
) -> Tuple[Optional[str], Set[str], Dict[str, Optional[float]]]:
    agreements = _regional_channel_agreements(window, channel_rows)
    profile = _montage_profile_for_task(task_id)
    primary = profile["primary_region"]

    def region_is_low(region: str) -> bool:
        channels = _MONTAGE_REGION_CHANNELS[region]
        if not all(key in channel_rows for key in channels):
            return False
        value = agreements.get(region)
        return value is not None and value < _MIN_PRIMARY_REGION_AGREEMENT

    if primary in _MONTAGE_REGION_CHANNELS and region_is_low(primary):
        return (
            f"low_{primary}_agreement",
            set(_MONTAGE_REGION_CHANNELS[primary]),
            agreements,
        )
    if primary == "frontal_occipital":
        low_regions = [
            region for region in ("frontal", "occipital")
            if region_is_low(region)
        ]
        if low_regions:
            affected = set()
            for region in low_regions:
                affected.update(_MONTAGE_REGION_CHANNELS[region])
            return "low_mixed_region_agreement", affected, agreements
    return None, set(), agreements


def _add_agreement_metadata(
    row: Dict[str, float],
    channel_rows: Dict[str, Dict[str, float]],
    agreements: Dict[str, Optional[float]],
    task_id: str = "",
) -> None:
    profile = _montage_profile_for_task(task_id)
    primary = profile["primary_region"]
    for region in _MONTAGE_REGION_CHANNELS:
        value = agreements.get(region)
        if value is not None and math.isfinite(float(value)):
            row[f"_{region}_channel_agreement"] = float(value)

    primary_values: List[float] = []
    if primary in _MONTAGE_REGION_CHANNELS:
        value = agreements.get(primary)
        if value is not None and math.isfinite(float(value)):
            primary_values.append(float(value))
    elif primary == "frontal_occipital":
        for region in ("frontal", "occipital"):
            value = agreements.get(region)
            if value is not None and math.isfinite(float(value)):
                primary_values.append(float(value))

    if primary_values:
        primary_agreement = float(sum(primary_values) / len(primary_values))
        row["_primary_channel_agreement"] = primary_agreement
        row["_primary_region_confidence"] = max(0.0, min(1.0, (primary_agreement + 1.0) / 2.0))
    elif primary in _MONTAGE_REGION_CHANNELS:
        present = sum(1 for key in _MONTAGE_REGION_CHANNELS[primary] if key in channel_rows)
        row["_primary_region_confidence"] = 0.5 if present == 1 else 0.0
    elif primary == "frontal_occipital":
        frontal = any(key in channel_rows for key in _MONTAGE_REGION_CHANNELS["frontal"])
        occipital = any(key in channel_rows for key in _MONTAGE_REGION_CHANNELS["occipital"])
        row["_primary_region_confidence"] = 0.5 if frontal and occipital else 0.0


def _rejection_reason_from_channel_reasons(reasons: List[str]) -> str:
    if reasons and all(reason == "flatline" for reason in reasons):
        return "flatline"
    if "not_worn" in reasons:
        return "not_worn"
    if "artifact" in reasons:
        return "artifact"
    if "flatline" in reasons:
        return "flatline"
    return "artifact"


def _montage_channel_rows_for_window(window, fs: int = _RAW_EEG_FS, apply_qc: bool = False) -> tuple:
    if not _NP_AVAILABLE:
        return {}, {key: "artifact" for key in MINDROVE_CHANNEL_ORDER}

    arr = _np.asarray(window, dtype=_np.float64)
    if arr.ndim != 2 or arr.shape[0] == 0 or arr.shape[1] < len(MINDROVE_CHANNEL_ORDER):
        return {}, {key: "artifact" for key in MINDROVE_CHANNEL_ORDER}

    channel_rows: Dict[str, Dict[str, float]] = {}
    reasons: Dict[str, Optional[str]] = {}
    for idx in range(len(MINDROVE_CHANNEL_ORDER)):
        key = MINDROVE_CHANNEL_ORDER[idx]
        channel_window = arr[:, idx]
        reason = _raw_window_qc(channel_window, fs=fs) if apply_qc else None
        reasons[key] = reason
        if reason is None:
            channel_rows[key] = _raw_window_to_features(channel_window, fs=fs)

    return channel_rows, reasons


def _multichannel_window_to_features(
    window,
    fs: int = _RAW_EEG_FS,
    apply_qc: bool = False,
    task_id: str = "",
):
    channel_rows, reasons_by_channel = _montage_channel_rows_for_window(window, fs, apply_qc)
    missing_reason = _missing_required_region_reason(channel_rows, task_id)
    if missing_reason is not None:
        return None, "artifact", reasons_by_channel
    agreement_reason, affected_channels, agreements = _low_primary_region_agreement(window, channel_rows, task_id)
    if channel_rows:
        row = _task_weighted_montage_features(channel_rows, task_id)
        _add_agreement_metadata(row, channel_rows, agreements, task_id)
        # Low agreement between two otherwise valid regional channels lowers
        # spatial confidence, but does not prove that the time-domain recording
        # is noisy or discontinuous.  Hard-rejecting it split valid recordings
        # into sub-20-second fragments, particularly in frontal Task 2 data.
        row["_primary_region_agreement_low"] = float(agreement_reason is not None)
        row["_low_agreement_channel_count"] = float(len(affected_channels))
        return row, None, reasons_by_channel

    rejected_reasons = [
        reason for reason in reasons_by_channel.values()
        if reason is not None
    ]
    return None, _rejection_reason_from_channel_reasons(rejected_reasons), reasons_by_channel


def _empty_montage_summary(task_id: str = "") -> Dict[str, Any]:
    profile = _montage_profile_for_task(task_id)
    return {
        "device": "MindRove",
        "task_id": task_id or "",
        "channels": [_MONTAGE_CHANNEL_DISPLAY[key] for key in MINDROVE_CHANNEL_ORDER],
        "regions": {
            region: [_MONTAGE_CHANNEL_DISPLAY[key] for key in channels]
            for region, channels in _MONTAGE_REGION_CHANNELS.items()
        },
        "primary_evidence_region": profile["primary_region"],
        "secondary_evidence_region": profile["secondary_region"],
        "window_count": 0,
        "channel_counts": {
            key: {"valid": 0, "seen": 0, "flatline": 0, "not_worn": 0, "artifact": 0}
            for key in MINDROVE_CHANNEL_ORDER
        },
        "region_counts": {
            region: {"valid": 0, "seen": 0}
            for region in _MONTAGE_REGION_CHANNELS
        },
        "spatial_values": {
            "corr_Fp1_Fp2": [],
            "corr_O1_O2": [],
            "corr_Fp_mean_O_mean": [],
        },
        "multi_channel_gain": {
            "used_frontal_consensus": False,
            "used_occipital_evidence": False,
            "used_spatial_contrast": False,
            "fallback_to_single_channel": True,
        },
    }


def _safe_corr(a, b) -> Optional[float]:
    if not _NP_AVAILABLE:
        return None
    try:
        ax = _np.asarray(a, dtype=_np.float64)
        bx = _np.asarray(b, dtype=_np.float64)
        if ax.size < 3 or bx.size < 3:
            return None
        if float(_np.std(ax)) <= 1e-12 or float(_np.std(bx)) <= 1e-12:
            return None
        value = float(_np.corrcoef(ax, bx)[0, 1])
        return value if math.isfinite(value) else None
    except Exception:
        return None


def _update_montage_summary(
    summary: Dict[str, Any],
    window,
    channel_rows: Dict[str, Dict[str, float]],
    reasons_by_channel: Dict[str, Optional[str]],
) -> None:
    if not summary or not _NP_AVAILABLE:
        return

    arr = _np.asarray(window, dtype=_np.float64)
    summary["window_count"] += 1

    for key in MINDROVE_CHANNEL_ORDER:
        counts = summary["channel_counts"][key]
        counts["seen"] += 1
        reason = reasons_by_channel.get(key)
        if key in channel_rows and reason is None:
            counts["valid"] += 1
        elif reason in ("flatline", "not_worn", "artifact"):
            counts[reason] += 1
        else:
            counts["artifact"] += 1

    for region, channels in _MONTAGE_REGION_CHANNELS.items():
        counts = summary["region_counts"][region]
        counts["seen"] += 1
        if any(key in channel_rows for key in channels):
            counts["valid"] += 1

    if arr.ndim == 2 and arr.shape[1] >= len(MINDROVE_CHANNEL_ORDER):
        fp_corr = _safe_corr(arr[:, 0], arr[:, 1])
        occ_corr = _safe_corr(arr[:, 2], arr[:, 3])
        fp_mean = _np.mean(arr[:, [0, 1]], axis=1)
        occ_mean = _np.mean(arr[:, [2, 3]], axis=1)
        fpo_corr = _safe_corr(fp_mean, occ_mean)
        if fp_corr is not None:
            summary["spatial_values"]["corr_Fp1_Fp2"].append(fp_corr)
        if occ_corr is not None:
            summary["spatial_values"]["corr_O1_O2"].append(occ_corr)
        if fpo_corr is not None:
            summary["spatial_values"]["corr_Fp_mean_O_mean"].append(fpo_corr)

    frontal_valid = any(key in channel_rows for key in _MONTAGE_REGION_CHANNELS["frontal"])
    occipital_valid = any(key in channel_rows for key in _MONTAGE_REGION_CHANNELS["occipital"])
    spatial_contrast = bool(_spatial_contrast_features(_region_feature_rows(channel_rows)))
    gain = summary["multi_channel_gain"]
    gain["used_frontal_consensus"] = gain["used_frontal_consensus"] or frontal_valid
    gain["used_occipital_evidence"] = gain["used_occipital_evidence"] or occipital_valid
    gain["used_spatial_contrast"] = gain["used_spatial_contrast"] or spatial_contrast
    gain["fallback_to_single_channel"] = False


def _quality_label(rate: float) -> str:
    if rate >= 0.80:
        return "high"
    if rate >= 0.50:
        return "medium"
    return "low"


def _finalize_montage_summary(summary: Dict[str, Any]) -> Dict[str, Any]:
    if not summary:
        return {}
    channel_quality: Dict[str, Dict[str, Any]] = {}
    for key, counts in summary["channel_counts"].items():
        seen = max(1, int(counts.get("seen", 0)))
        valid = int(counts.get("valid", 0))
        label = _MONTAGE_CHANNEL_DISPLAY[key]
        channel_quality[label] = {
            "valid_windows": valid,
            "seen_windows": int(counts.get("seen", 0)),
            "valid_rate": round(valid / seen, 4),
            "flatline": int(counts.get("flatline", 0)),
            "not_worn": int(counts.get("not_worn", 0)),
            "artifact": int(counts.get("artifact", 0)),
        }

    regional_reliability: Dict[str, str] = {}
    regional_quality: Dict[str, Dict[str, Any]] = {}
    for region, counts in summary["region_counts"].items():
        seen = max(1, int(counts.get("seen", 0)))
        valid = int(counts.get("valid", 0))
        rate = valid / seen
        regional_reliability[region] = _quality_label(rate)
        regional_quality[region] = {
            "valid_windows": valid,
            "seen_windows": int(counts.get("seen", 0)),
            "valid_rate": round(rate, 4),
        }

    spatial_evidence = {}
    for name, values in summary["spatial_values"].items():
        spatial_evidence[name] = (
            round(float(_np.mean(values)), 4)
            if _NP_AVAILABLE and values else None
        )

    return {
        "device": summary["device"],
        "channels": summary["channels"],
        "regions": summary["regions"],
        "primary_evidence_region": summary["primary_evidence_region"],
        "secondary_evidence_region": summary["secondary_evidence_region"],
        "channel_quality": channel_quality,
        "regional_quality": regional_quality,
        "regional_reliability": regional_reliability,
        "spatial_evidence": spatial_evidence,
        "multi_channel_gain": dict(summary["multi_channel_gain"]),
    }


def _merge_montage_summaries(summaries: List[Dict[str, Any]]) -> Dict[str, Any]:
    summaries = [s for s in summaries if s]
    if not summaries:
        return {}

    merged = _empty_montage_summary()
    primary_regions = []
    for summary in summaries:
        primary_regions.append(summary.get("primary_evidence_region", "balanced"))
        for key in MINDROVE_CHANNEL_ORDER:
            target = merged["channel_counts"][key]
            source = summary.get("channel_counts", {}).get(key)
            if source is None:
                source = summary.get("channel_quality", {}).get(_MONTAGE_CHANNEL_DISPLAY[key], {})
                target["valid"] += int(source.get("valid_windows", 0))
                target["seen"] += int(source.get("seen_windows", 0))
                target["flatline"] += int(source.get("flatline", 0))
                target["not_worn"] += int(source.get("not_worn", 0))
                target["artifact"] += int(source.get("artifact", 0))
            else:
                for metric in target:
                    target[metric] += int(source.get(metric, 0))
        for region in _MONTAGE_REGION_CHANNELS:
            target = merged["region_counts"][region]
            source = summary.get("region_counts", {}).get(region)
            if source is None:
                source = summary.get("regional_quality", {}).get(region, {})
                target["valid"] += int(source.get("valid_windows", 0))
                target["seen"] += int(source.get("seen_windows", 0))
            else:
                for metric in target:
                    target[metric] += int(source.get(metric, 0))
        if "spatial_values" in summary:
            for name, values in summary.get("spatial_values", {}).items():
                merged["spatial_values"][name].extend(values)
        else:
            for name, value in summary.get("spatial_evidence", {}).items():
                if value is not None:
                    merged["spatial_values"][name].append(float(value))
        merged["window_count"] += int(
            summary.get(
                "window_count",
                max(
                    [0]
                    + [
                        int(item.get("seen_windows", 0))
                        for item in summary.get("channel_quality", {}).values()
                    ]
                ),
            )
        )
        for key, value in summary.get("multi_channel_gain", {}).items():
            if key == "fallback_to_single_channel":
                merged["multi_channel_gain"][key] = merged["multi_channel_gain"][key] and bool(value)
            else:
                merged["multi_channel_gain"][key] = merged["multi_channel_gain"][key] or bool(value)

    unique_primary = sorted(set(primary_regions))
    merged["primary_evidence_region"] = unique_primary[0] if len(unique_primary) == 1 else "task_specific"
    return _finalize_montage_summary(merged)


def _montage_export_fields(montage_summary: Dict[str, Any]) -> Dict[str, Any]:
    if not montage_summary:
        return {}
    return {
        "headset_scope": "MindRove sparse montage: Fp1/Fp2 frontal + O1/O2 occipital",
        "montage": {
            "device": montage_summary["device"],
            "channels": montage_summary["channels"],
            "regions": montage_summary["regions"],
        },
        "channel_quality": montage_summary["channel_quality"],
        "regional_reliability": montage_summary["regional_reliability"],
        "primary_evidence_region": montage_summary["primary_evidence_region"],
        "multi_channel_gain": montage_summary["multi_channel_gain"],
        "spatial_evidence": montage_summary["spatial_evidence"],
    }


def _multichannel_to_feature_rows(
    samples: List,
    fs: int = _RAW_EEG_FS,
    apply_qc: bool = False,
    task_id: str = "",
    return_montage: bool = False,
    source_start_sample_index: int = 0,
    transport_segment_id: str = "0",
) -> tuple:
    counters = _empty_window_qc()

    arr = _coerce_multichannel_raw_samples(samples)
    window_n = _raw_window_samples(fs)
    step_n = _raw_step_samples(fs)
    montage_summary = _empty_montage_summary(task_id) if return_montage else None
    if arr is None or len(arr) < window_n:
        counters = _finalize_window_qc(
            counters,
            window_seconds=window_n / float(fs),
            step_seconds=step_n / float(fs),
        )
        if return_montage:
            return [], counters, _finalize_montage_summary(montage_summary)
        return [], counters

    rows: List[Dict[str, float]] = []
    for start in range(0, len(arr) - window_n + 1, step_n):
        window = arr[start:start + window_n, :]
        row, reason, reasons_by_channel = _multichannel_window_to_features(
            window,
            fs=fs,
            apply_qc=apply_qc,
            task_id=task_id,
        )
        if montage_summary is not None:
            channel_rows, _ = _montage_channel_rows_for_window(window, fs, apply_qc)
            _update_montage_summary(montage_summary, window, channel_rows, reasons_by_channel)
        if row:
            absolute_start = int(source_start_sample_index) + start
            absolute_end = absolute_start + window_n
            _annotate_feature_window(
                row,
                segment_id=str(transport_segment_id),
                start_sample_index=absolute_start,
                end_sample_index_exclusive=absolute_end,
                start_seconds=absolute_start / float(fs),
                end_seconds=absolute_end / float(fs),
            )
            rows.append(row)
            _record_window_qc(counters, True)
        else:
            _record_window_qc(counters, False, reason)

    counters = _finalize_window_qc(
        counters,
        window_seconds=window_n / float(fs),
        step_seconds=step_n / float(fs),
    )

    if return_montage:
        return rows, counters, _finalize_montage_summary(montage_summary)
    return rows, counters


def _raw_to_feature_windows(raw_samples: List, fs: int = _RAW_EEG_FS) -> List[Dict[str, float]]:
    if not _NP_AVAILABLE:
        return []
    return [_raw_window_to_features(window, fs) for window in _iter_raw_windows(raw_samples, fs)]


def _baseline_feature_rows(
    samples: List,
    task_id: str = "",
    return_montage: bool = False,
    fs: Optional[int] = None,
    source_start_sample_index: int = 0,
    transport_segment_id: str = "0",
) -> tuple:
    counters = _empty_window_qc()
    if not samples:
        counters = _finalize_window_qc(counters)
        if return_montage:
            return [], counters, {}
        return [], counters
    multichannel_samples = _multichannel_raw_subset(samples)
    if multichannel_samples:
        _log_mixed_sample_use("Analyze", samples, "multichannel", task_id=task_id)
        rows: List[Dict[str, float]] = []
        run_qc: List[Dict[str, Any]] = []
        run_montages: List[Dict[str, Any]] = []
        for run_index, (run_start, run) in enumerate(
            _contiguous_sample_runs_with_offsets(samples, _is_multichannel_raw_sample)
        ):
            run_rows, qc, montage = _multichannel_to_feature_rows(
                run,
                fs=int(fs or _RAW_EEG_FS),
                apply_qc=True,
                task_id=task_id,
                return_montage=True,
                source_start_sample_index=int(source_start_sample_index) + run_start,
                transport_segment_id=f"{transport_segment_id}:{run_index}",
            )
            rows.extend(run_rows)
            run_qc.append(qc)
            if montage:
                run_montages.append(montage)
        counters = _merge_qc_counters(*run_qc)
        if return_montage:
            return rows, counters, _merge_montage_summaries(run_montages)
        return rows, counters
    scalar_samples = _scalar_raw_subset(samples)
    if scalar_samples:
        _log_mixed_sample_use("Analyze", samples, "scalar", task_id=task_id)
        rows: List[Dict[str, float]] = []
        scalar_fs = int(fs or _LEGACY_RAW_EEG_FS)
        run_qc: List[Dict[str, Any]] = []
        for run_index, (run_start, run) in enumerate(_contiguous_sample_runs_with_offsets(
            samples,
            lambda sample: isinstance(sample, (int, float)),
        )):
            current_qc = _empty_window_qc()
            window_n = _raw_window_samples(scalar_fs)
            step_n = _raw_step_samples(scalar_fs)
            for window_index, window in enumerate(_iter_raw_windows(run, fs=scalar_fs)):
                reason = _raw_window_qc(window, fs=scalar_fs)
                if reason is None:
                    row = _raw_window_to_features(window, fs=scalar_fs)
                    absolute_start = (
                        int(source_start_sample_index)
                        + run_start
                        + window_index * step_n
                    )
                    _annotate_feature_window(
                        row,
                        segment_id=f"{transport_segment_id}:{run_index}",
                        start_sample_index=absolute_start,
                        end_sample_index_exclusive=absolute_start + window_n,
                        start_seconds=absolute_start / float(scalar_fs),
                        end_seconds=(absolute_start + window_n) / float(scalar_fs),
                    )
                    rows.append(row)
                    _record_window_qc(current_qc, True)
                else:
                    _record_window_qc(current_qc, False, reason)
            run_qc.append(_finalize_window_qc(
                current_qc,
                window_seconds=_raw_window_samples(scalar_fs) / float(scalar_fs),
                step_seconds=_raw_step_samples(scalar_fs) / float(scalar_fs),
            ))
        counters = _merge_qc_counters(*run_qc)
        if return_montage:
            return rows, counters, {}
        return rows, counters

    feature_samples = _feature_dict_subset(samples)
    if feature_samples:
        _log_mixed_sample_use("Analyze", samples, "feature_dict", task_id=task_id)
        rows: List[Dict[str, float]] = []
        run_qc: List[Dict[str, Any]] = []
        for run_index, (run_start, run) in enumerate(_contiguous_sample_runs_with_offsets(
            samples,
            lambda sample: (
                isinstance(sample, dict)
                and not _is_multichannel_raw_sample(sample)
            ),
        )):
            current_rows = _extract_features(run)
            for row_index, row in enumerate(current_rows):
                absolute_index = int(source_start_sample_index) + run_start + row_index
                start_seconds = absolute_index * _WINDOW_STEP_SEC
                _annotate_feature_window(
                    row,
                    segment_id=f"{transport_segment_id}:{run_index}",
                    start_sample_index=absolute_index,
                    end_sample_index_exclusive=absolute_index + 1,
                    start_seconds=start_seconds,
                    end_seconds=start_seconds + _WINDOW_DURATION_SEC,
                )
            rows.extend(current_rows)
            current_qc = _empty_window_qc()
            for _ in current_rows:
                _record_window_qc(current_qc, True)
            run_qc.append(_finalize_window_qc(current_qc))
        counters = _merge_qc_counters(*run_qc)
    else:
        rows = _extract_features(samples)
        for row_index, row in enumerate(rows):
            absolute_index = int(source_start_sample_index) + row_index
            start_seconds = absolute_index * _WINDOW_STEP_SEC
            _annotate_feature_window(
                row,
                segment_id=str(transport_segment_id),
                start_sample_index=absolute_index,
                end_sample_index_exclusive=absolute_index + 1,
                start_seconds=start_seconds,
                end_seconds=start_seconds + _WINDOW_DURATION_SEC,
            )
            _record_window_qc(counters, True)
        counters = _finalize_window_qc(counters)
    if return_montage:
        return rows, counters, {}
    return rows, counters


def _merge_qc_counters(*counters_list: Dict[str, Any]) -> Dict[str, Any]:
    merged = _empty_window_qc()
    merged.pop("_current_contiguous_clean_windows", None)
    for counters in counters_list:
        for key in ("kept", "rejected", "not_worn", "artifact", "flatline", "total_windows"):
            merged[key] += int((counters or {}).get(key, 0))
        merged["max_contiguous_clean_windows"] = max(
            int(merged.get("max_contiguous_clean_windows", 0)),
            int((counters or {}).get("max_contiguous_clean_windows", 0)),
        )
    max_seconds = max(
        (float((counters or {}).get("max_contiguous_clean_seconds", 0.0)) for counters in counters_list),
        default=0.0,
    )
    merged.update({
        "window_seconds": _RAW_WINDOW_SECONDS,
        "window_overlap": _RAW_WINDOW_OVERLAP,
        "step_seconds": _RAW_WINDOW_SECONDS * (1.0 - _RAW_WINDOW_OVERLAP),
        "max_contiguous_clean_seconds": round(max_seconds, 3),
        "minimum_contiguous_clean_seconds": _MIN_CONTIGUOUS_CLEAN_SECONDS,
        "meets_contiguous_clean_minimum": max_seconds >= _MIN_CONTIGUOUS_CLEAN_SECONDS,
    })
    return merged


def _feature_rows_for_transport_segments(
    samples: List,
    metadata: Any = None,
    *,
    task_id: str = "",
    fs: Optional[int] = None,
) -> Tuple[List[Dict[str, float]], Dict[str, Any], Dict[str, Any]]:
    """Extract clean windows per declared transport run without gap stitching."""
    segments, segmentation = _transport_segments_from_metadata(metadata, len(samples or []))
    all_rows: List[Dict[str, float]] = []
    segment_qc: List[Dict[str, Any]] = []
    segment_montages: List[Dict[str, Any]] = []
    segment_results: List[Dict[str, Any]] = []

    for segment in segments:
        segment_id = int(segment["segment_id"])
        start = int(segment["start_sample_index"])
        end = int(segment["end_sample_index_exclusive"])
        rows, qc, montage = _baseline_feature_rows(
            list((samples or [])[start:end]),
            task_id=task_id,
            return_montage=True,
            fs=fs,
            source_start_sample_index=start,
            transport_segment_id=str(segment_id),
        )
        # The submitted sample array is compacted, while a declared transport
        # segment may start later on the real recording clock after a dropout.
        # Shift the already annotated windows onto that clock so phase summaries
        # cannot move post-gap samples into an earlier phase.
        declared_start_ms = segment.get("start_elapsed_ms")
        if declared_start_ms is not None:
            segment_samples = list((samples or [])[start:end])
            raw_like = bool(
                _multichannel_raw_subset(segment_samples)
                or _scalar_raw_subset(segment_samples)
            )
            default_start_seconds = (
                start / float(fs or (_RAW_EEG_FS if raw_like else _LEGACY_RAW_EEG_FS))
                if raw_like
                else start * _WINDOW_STEP_SEC
            )
            timing_shift_seconds = float(declared_start_ms) / 1000.0 - default_start_seconds
            for row in rows:
                row["_window_start_seconds"] = (
                    float(row.get("_window_start_seconds", 0.0)) + timing_shift_seconds
                )
                row["_window_end_seconds"] = (
                    float(row.get("_window_end_seconds", 0.0)) + timing_shift_seconds
                )
        all_rows.extend(rows)
        segment_qc.append(qc)
        if montage:
            segment_montages.append(montage)
        segment_results.append({
            **segment,
            "sample_count": end - start,
            "clean_window_count": len(rows),
            "max_contiguous_clean_seconds": float(qc.get("max_contiguous_clean_seconds", 0.0)),
        })

    merged_qc = _merge_qc_counters(*segment_qc)
    segmentation["segments"] = segment_results
    merged_qc["transport_segmentation"] = segmentation
    montage_summary = _merge_montage_summaries(segment_montages)
    return all_rows, merged_qc, montage_summary


def _baseline_feature_rows_from_phases(
    ec_samples: List,
    eo_samples: Optional[List] = None,
    task_id: str = "",
    return_montage: bool = False,
) -> tuple:
    ec_rows, ec_qc, ec_montage = _baseline_feature_rows(
        ec_samples,
        task_id=task_id,
        return_montage=True,
    )
    eo_rows: List[Dict[str, float]] = []
    eo_qc = _finalize_window_qc(_empty_window_qc())
    eo_montage: Dict[str, Any] = {}
    if eo_samples:
        eo_rows, eo_qc, eo_montage = _baseline_feature_rows(
            eo_samples,
            task_id=task_id,
            return_montage=True,
        )

    rows = list(ec_rows) + list(eo_rows)
    qc = _merge_qc_counters(ec_qc, eo_qc)
    if return_montage:
        montage = _merge_montage_summaries([
            item for item in (ec_montage, eo_montage) if item
        ])
        return rows, qc, montage
    return rows, qc


def _samples_to_feature_rows(samples: List, task_id: str = "") -> List[Dict[str, float]]:
    if not samples:
        return []
    multichannel_samples = _multichannel_raw_subset(samples)
    if multichannel_samples:
        _log_mixed_sample_use("Analyze", samples, "multichannel", task_id=task_id)
        rows, _ = _multichannel_to_feature_rows(multichannel_samples, apply_qc=True, task_id=task_id)
        return rows
    scalar_samples = _scalar_raw_subset(samples)
    if scalar_samples:
        _log_mixed_sample_use("Analyze", samples, "scalar", task_id=task_id)
        return _raw_to_feature_windows(scalar_samples, fs=_LEGACY_RAW_EEG_FS)
    feature_samples = _feature_dict_subset(samples)
    if feature_samples:
        _log_mixed_sample_use("Analyze", samples, "feature_dict", task_id=task_id)
    return _extract_features(feature_samples or samples)


def _maybe_convert_raw(samples: List) -> List[Dict]:
    """If samples is a list of numbers (raw EEG), convert to raw feature windows.
    If already a list of dicts (band-power), return as-is."""
    if not samples:
        return samples
    multichannel_samples = _multichannel_raw_subset(samples)
    if multichannel_samples:
        _log_mixed_sample_use("Analyze", samples, "multichannel")
        rows, _ = _multichannel_to_feature_rows(multichannel_samples, apply_qc=True)
        return rows
    scalar_samples = _scalar_raw_subset(samples)
    if scalar_samples:
        _log_mixed_sample_use("Analyze", samples, "scalar")
        return _raw_to_feature_windows(scalar_samples, fs=_LEGACY_RAW_EEG_FS)
    feature_samples = _feature_dict_subset(samples)
    if feature_samples:
        _log_mixed_sample_use("Analyze", samples, "feature_dict")
    return feature_samples or samples
_ALPHA              = 0.05
_FDR_ALPHA          = 0.05
_N_PERM             = 1000
_MIN_PERCENT_CHANGE      = 10.0  # raw-power features
_MIN_PERCENT_CHANGE_REL  =  5.0  # relative/ratio features (bounded 0-1, smaller natural range)

# Block aggregation constants. Feature windows are 2 s with a 1 s step (50%
# overlap); block sizing therefore uses the step rather than window duration.
_BLOCK_SECONDS       = 8.0
_WINDOW_DURATION_SEC = _RAW_WINDOW / _RAW_EEG_FS   # 2.0 s
_WINDOW_STEP_SEC     = _RAW_STEP / _RAW_EEG_FS     # 1.0 s
_WINDOWS_PER_BLOCK   = max(1, round(_BLOCK_SECONDS / _WINDOW_STEP_SEC))  # 8

# Derived band definitions: (name, [source_tgam_keys], fraction_of_source, center_hz)
# theta1/theta2 are approximated as 50% of theta.
_DERIVED_BAND_DEFS = [
    ("delta",   ["delta"],                  1.0,   2.0),
    ("theta",   ["theta"],                  1.0,   6.0),
    ("theta1",  ["theta"],                  0.5,   5.0),
    ("theta2",  ["theta"],                  0.5,   7.0),
    ("alpha",   ["lowAlpha", "highAlpha"],  1.0,  10.5),
    ("beta",    ["lowBeta",  "highBeta"],   1.0,  21.5),
    ("beta1",   ["lowBeta"],                1.0,  16.5),
    ("beta2",   ["highBeta"],               1.0,  25.0),
    ("gamma",   ["lowGamma", "midGamma"],   1.0,  37.5),
]


def _binary_entropy(p: float) -> float:
    """Binary entropy H(p) = -p·log2(p) - (1-p)·log2(1-p). Ranges 0–1."""
    p = max(1e-10, min(1.0 - 1e-10, p))
    return -p * math.log2(p) - (1.0 - p) * math.log2(1.0 - p)


def _extract_features(samples: List[Dict]) -> List[Dict[str, float]]:
    """Convert TGAM band-power samples to 70-feature dicts.

    Features per derived band (9 bands × 7 = 63):
      {b}_power, {b}_power_raw, {b}_relative,
      {b}_peak_freq, {b}_peak_amp, {b}_peak_rel_amp, {b}_entropy

    Ratios (4): alpha_theta_ratio, beta_alpha_ratio, beta2_beta1_ratio, theta2_theta1_ratio
    Scalars (3): total_power, _emg_guard, _gamma_evaluated
    Total: 70
    """
    rows: List[Dict[str, float]] = []
    for s in samples:
        raw = {b: max(0.0, float(s.get(b, 0))) for b in _BANDS}
        total_power = sum(raw.values()) or 1.0

        # Compute derived band powers
        bp: Dict[str, float] = {}
        for bname, sources, frac, _center in _DERIVED_BAND_DEFS:
            bp[bname] = sum(raw.get(src, 0.0) for src in sources) * frac

        total_derived = sum(bp.values()) or 1.0
        mean_bp       = total_derived / len(_DERIVED_BAND_DEFS)

        row: Dict[str, float] = {}

        for bname, sources, _frac, center_hz in _DERIVED_BAND_DEFS:
            p   = bp[bname]
            rel = p / total_derived
            row[f"{bname}_power"]     = p
            row[f"{bname}_power_raw"] = p
            row[f"{bname}_relative"]  = rel
            # Peak freq: power-weighted avg of constituent TGAM-band peaks.
            # Accurate when input came from _raw_to_bp_windows (contains real FFT peaks);
            # falls back to band-centre when the TGAM chip sends pre-computed powers.
            src_powers = [raw.get(src, 0.0) for src in sources]
            src_pf     = [s.get(f"{src}_peak_freq", center_hz) for src in sources]
            src_pa     = [s.get(f"{src}_peak_amp",  0.0)       for src in sources]
            total_src  = sum(src_powers) or 1e-12
            row[f"{bname}_peak_freq"]    = sum(sp * pf for sp, pf in zip(src_powers, src_pf)) / total_src
            row[f"{bname}_peak_amp"]     = max(src_pa) if src_pa else 0.0
            row[f"{bname}_peak_rel_amp"] = row[f"{bname}_peak_amp"] / (mean_bp + 1e-9)
            # Entropy: use stored per-source Shannon entropy (from _raw_to_bp_windows) when
            # available; power-weighted average across source bands.  Falls back to binary
            # entropy on relative power when the TGAM chip provides pre-computed powers.
            has_stored_ent = any(f"{src}_entropy" in s for src in sources)
            if has_stored_ent:
                src_ents = [s.get(f"{src}_entropy", 0.0) for src in sources]
                row[f"{bname}_entropy"] = (
                    sum(sp * ent for sp, ent in zip(src_powers, src_ents)) / (total_src + 1e-12)
                )
            else:
                row[f"{bname}_entropy"] = _binary_entropy(rel)

        # Ratios
        row["alpha_theta_ratio"]   = bp["alpha"]  / (bp["theta"]  + 1e-9)
        row["beta_alpha_ratio"]    = bp["beta"]   / (bp["alpha"]  + 1e-9)
        row["beta2_beta1_ratio"]   = bp["beta2"]  / (bp["beta1"]  + 1e-9)
        row["theta2_theta1_ratio"] = bp["theta2"] / (bp["theta1"] + 1e-9)

        # Scalars
        row["total_power"] = total_power

        # EMG guard: use value stored by _raw_to_bp_windows when available (spectral-slope
        # based); otherwise fall back to the simple power-ratio heuristic.
        pre_emg = s.get("_emg_guard", None)
        if pre_emg is not None:
            emg_flag = int(pre_emg)
        else:
            emg_flag = int(bp["gamma"] > bp["beta2"] * 2.0 + 10.0)

        # When EMG guard fires, zero out all gamma features (mirrors legacy behaviour)
        if emg_flag:
            for suf in ("_power", "_power_raw", "_relative", "_peak_freq",
                        "_peak_amp", "_peak_rel_amp", "_entropy"):
                row[f"gamma{suf}"] = 0.0

        row["_emg_guard"]       = float(emg_flag)
        row["_gamma_evaluated"] = float(1 - emg_flag)

        rows.append(row)
    return rows


def _welch_t(a: List[float], b: List[float]):
    """Welch's t-test. Returns (t, p)."""
    if len(a) < 2 or len(b) < 2:
        return 0.0, 1.0
    if _series_is_near_constant(a) or _series_is_near_constant(b):
        return 0.0, 1.0
    if _SCIPY_AVAILABLE:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                t, p = _scipy_stats.ttest_ind(a, b, equal_var=False)
            return (0.0, 1.0) if math.isnan(p) else (float(t), float(p))
        except Exception:
            pass
    # Fallback Welch's t-test (no scipy)
    n1, n2 = len(a), len(b)
    m1 = sum(a) / n1;  m2 = sum(b) / n2
    v1 = sum((x - m1)**2 for x in a) / (n1 - 1) if n1 > 1 else 0.0
    v2 = sum((x - m2)**2 for x in b) / (n2 - 1) if n2 > 1 else 0.0
    se = math.sqrt(v1 / n1 + v2 / n2) or 1e-9
    t  = (m1 - m2) / se
    # Welch–Satterthwaite df
    num = (v1/n1 + v2/n2)**2
    den = (v1/n1)**2/(n1-1) + (v2/n2)**2/(n2-1) if (n1 > 1 and n2 > 1) else 1.0
    df  = num / den if den else 1.0
    # approximate p via normal for large df; otherwise use 0.5 guard
    if _SCIPY_AVAILABLE:
        p = float(_scipy_stats.t.sf(abs(t), df) * 2)
    else:
        p = min(1.0, max(0.0, 2.0 * (1.0 - 0.5 * (1 + math.erf(abs(t) / math.sqrt(2))))))
    return t, p


def _cohens_d_vals(a: List[float], b: List[float]) -> float:
    """Cohen's d (a vs b)."""
    if len(a) < 2 or len(b) < 2:
        return 0.0
    ma = sum(a) / len(a);  mb = sum(b) / len(b)
    va = sum((x - ma)**2 for x in a) / (len(a) - 1)
    vb = sum((x - mb)**2 for x in b) / (len(b) - 1)
    return (ma - mb) / (math.sqrt((va + vb) / 2) or 1e-9)


def _series_is_near_constant(values: List[float]) -> bool:
    """True when a sample series is too flat for stable inferential testing."""
    if len(values) < 2:
        return True
    lo = min(values)
    hi = max(values)
    scale = max(1.0, abs(lo), abs(hi), abs(sum(values) / len(values)))
    tol = max(_INFERENTIAL_ABS_TOL, _INFERENTIAL_REL_TOL * scale)
    return (hi - lo) <= tol


def _degenerate_feature_mask(mat: "_np.ndarray") -> "_np.ndarray":
    """Column mask for features that are too flat for stable Welch tests."""
    if mat.shape[0] < 2:
        return _np.ones(mat.shape[1], dtype=bool)
    col_min = _np.min(mat, axis=0)
    col_max = _np.max(mat, axis=0)
    col_mean = _np.abs(_np.mean(mat, axis=0))
    col_scale = _np.maximum(1.0, _np.maximum(_np.abs(col_min), _np.maximum(_np.abs(col_max), col_mean)))
    tol = _np.maximum(_INFERENTIAL_ABS_TOL, _INFERENTIAL_REL_TOL * col_scale)
    return (col_max - col_min) <= tol


def _bh_fdr(p_values: List[float]) -> List[float]:
    """Benjamini-Hochberg FDR correction. Returns q-values in the same order."""
    n = len(p_values)
    if n == 0:
        return []
    idx_sorted = sorted(range(n), key=lambda i: p_values[i])
    q = [1.0] * n
    prev_q = 1.0
    for rank, i in enumerate(reversed(idx_sorted), 1):
        q_val = p_values[i] * n / (n - rank + 1)
        prev_q = min(q_val, prev_q)
        q[i] = prev_q
    return q


def _fisher_combined(p_values: List[float]):
    """Fisher's combined probability test. Returns (stat, p, df)."""
    valid = [p for p in p_values if p is not None and 0 < p <= 1.0]
    if not valid:
        return None, None, None
    stat = -2.0 * sum(math.log(p) for p in valid)
    df   = 2 * len(valid)
    if _SCIPY_AVAILABLE:
        p = float(_scipy_chi2.sf(stat, df))
    else:
        # Approximate via normal (good for large df)
        z = (stat - df) / math.sqrt(2 * df)
        p = max(0.0, min(1.0, 0.5 * (1 - math.erf(z / math.sqrt(2)))))
    return stat, p, float(df)


def _pearson_r(xs: List[float], ys: List[float]) -> float:
    """Pearson correlation coefficient between two equal-length vectors."""
    n = len(xs)
    if n < 2:
        return 0.0
    mx = sum(xs) / n;  my = sum(ys) / n
    num = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    dx  = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy  = math.sqrt(sum((y - my) ** 2 for y in ys))
    denom = dx * dy
    return num / denom if denom > 1e-12 else 0.0


def _km_fisher(fisher_stat: Optional[float], fnames: List[str],
               all_rows: List[Dict]) -> tuple:
    """Kost–McDermott correction for correlated Fisher statistics.

    VECTORISED: builds a (k × n_rows) matrix and computes all pairwise Pearson
    correlations via numpy.corrcoef in one call instead of k*(k-1)/2 Python loops.
    """
    k = len(fnames)
    if fisher_stat is None or k <= 1 or len(all_rows) < 2:
        return fisher_stat, None, float(2 * max(k, 1)), None, None

    # ── Build feature matrix (k × n) and compute full correlation matrix ──────
    if _NP_AVAILABLE:
        try:
            mat  = _np.array([[float(r.get(f, 0.0)) for r in all_rows]
                               for f in fnames], dtype=float)   # (k, n)
            if mat.shape[1] < 2:
                return fisher_stat, None, float(2 * k), None, None
            # Rank-transform rows for Spearman correlation (matches legacy pandas .corr(method='spearman'))
            _ranked = _np.argsort(_np.argsort(mat, axis=1), axis=1).astype(float) + 1.0
            corr = _np.corrcoef(_ranked)                        # (k, k)
            corr = _np.nan_to_num(corr, nan=0.0, posinf=0.0, neginf=0.0)
            # Extract upper triangle (excludes diagonal)
            ui, uj = _np.triu_indices(k, k=1)
            r_vals  = corr[ui, uj]                              # (n_pairs,)
            r_sum   = float(r_vals.sum())
            r_count = len(r_vals)
            cov_sum = float((3.263 * r_vals +
                             0.710 * r_vals ** 2 +
                             0.027 * r_vals ** 3).sum())
            mean_r  = r_sum / r_count if r_count > 0 else 0.0
        except Exception:
            # Fallback to Python loops
            col     = {f: [float(r.get(f, 0.0)) for r in all_rows] for f in fnames}
            r_sum = r_count = cov_sum = 0.0
            for i in range(k):
                for j in range(i + 1, k):
                    ci, cj = col[fnames[i]], col[fnames[j]]
                    nn = min(len(ci), len(cj))
                    r  = _pearson_r(ci[:nn], cj[:nn])
                    r_sum   += r;  r_count += 1
                    cov_sum += 3.263 * r + 0.710 * r ** 2 + 0.027 * r ** 3
            mean_r = r_sum / r_count if r_count > 0 else 0.0
    else:
        col     = {f: [float(r.get(f, 0.0)) for r in all_rows] for f in fnames}
        r_sum = r_count = cov_sum = 0.0
        for i in range(k):
            for j in range(i + 1, k):
                ci, cj = col[fnames[i]], col[fnames[j]]
                nn = min(len(ci), len(cj))
                r  = _pearson_r(ci[:nn], cj[:nn])
                r_sum   += r;  r_count += 1
                cov_sum += 3.263 * r + 0.710 * r ** 2 + 0.027 * r ** 3
        mean_r = r_sum / r_count if r_count > 0 else 0.0

    mu       = 2.0 * k
    sigma_sq = 4.0 * k + 2.0 * cov_sum
    if sigma_sq <= 0:
        return fisher_stat, None, float(2 * k), mean_r, 1.0
    c        = sigma_sq / (2.0 * mu)
    df       = max(1.0, (2.0 * mu ** 2) / sigma_sq)
    adj_stat = fisher_stat / c
    if _SCIPY_AVAILABLE:
        km_p = float(_scipy_chi2.sf(adj_stat, df))
    else:
        z    = (adj_stat - df) / math.sqrt(2 * df)
        km_p = max(0.0, min(1.0, 0.5 * (1 - math.erf(z / math.sqrt(2)))))
    km_df_ratio = df / (2.0 * k)
    return adj_stat, km_p, df, mean_r, km_df_ratio


def _sum_p_perm(task_rows: List[Dict], baseline_rows: List[Dict], label: str = "") -> tuple:
    """SumP permutation test. Returns (observed_sum_p, perm_p).

    VECTORISED: pre-extracts a (n_total × n_features) numpy matrix once,
    then uses scipy.stats.ttest_ind with axis=0 to test all features in a
    single call per permutation instead of n_features separate calls.
    Reduces ~70,000 individual t-tests to ~1,000 vectorised ones.
    """
    if len(task_rows) < 2 or len(baseline_rows) < 2:
        return None, 1.0

    # Internal features (prefixed _) are meta-flags — exclude from test
    fnames = [f for f in task_rows[0].keys() if not f.startswith("_")]
    if not fnames:
        return None, 1.0

    pool_rows = task_rows + baseline_rows
    n_task    = len(task_rows)
    n_total   = len(pool_rows)
    context   = label or "combined"

    if _NP_AVAILABLE:
        # ── Fast numpy path ──────────────────────────────────────────────────
        mat = _np.array([[float(r.get(f, 0.0)) for f in fnames]
                          for r in pool_rows], dtype=float)   # (n_total, n_feat)
        observed_deg_mask = _degenerate_feature_mask(mat[:n_task]) | _degenerate_feature_mask(mat[n_task:])
        observed_deg_names = [fnames[i] for i, flag in enumerate(observed_deg_mask) if flag]
        if observed_deg_names:
            _debug_log(
                "DEGENERATE",
                f"SumP {context}: skipping {len(observed_deg_names)}/{len(fnames)} near-constant features -> {_feature_sample(observed_deg_names)}",
            )

        def _sum_p_vec(t_idx: "_np.ndarray", b_idx: "_np.ndarray") -> float:
            p_arr = _np.ones(len(fnames), dtype=float)
            deg_mask = _degenerate_feature_mask(mat[t_idx]) | _degenerate_feature_mask(mat[b_idx])
            valid_mask = ~deg_mask
            if not _np.any(valid_mask):
                return float(p_arr.sum())
            if _SCIPY_AVAILABLE:
                try:
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore", RuntimeWarning)
                        _, valid_p = _scipy_stats.ttest_ind(
                            mat[t_idx][:, valid_mask],
                            mat[b_idx][:, valid_mask],
                            axis=0,
                            equal_var=False,
                        )
                    p_arr[valid_mask] = _np.where(_np.isfinite(valid_p), valid_p, 1.0)
                    return float(p_arr.sum())
                except Exception:
                    pass
            # Pure-numpy Welch fallback (approximate, avoids scipy import failure)
            a = mat[t_idx][:, valid_mask]
            b = mat[b_idx][:, valid_mask]
            n1, n2 = a.shape[0], b.shape[0]
            m1, m2 = a.mean(0), b.mean(0)
            v1 = a.var(0, ddof=1);  v2 = b.var(0, ddof=1)
            se = _np.sqrt(v1 / n1 + v2 / n2) + 1e-12
            t_stat = _np.abs((m1 - m2) / se)
            # Estimate p via standard normal (over-estimates df but is fast)
            p_arr[valid_mask] = 2.0 * (1.0 - 0.5 * (1.0 + _np.vectorize(math.erf)(t_stat / math.sqrt(2))))
            return float(p_arr.sum())

        rng         = _np.random.RandomState(42)
        idx_all     = _np.arange(n_total)
        obs_sum     = _sum_p_vec(idx_all[:n_task], idx_all[n_task:])
        count_le    = 0
        for _ in range(_N_PERM):
            rng.shuffle(idx_all)
            if _sum_p_vec(idx_all[:n_task], idx_all[n_task:]) <= obs_sum:
                count_le += 1
        return obs_sum, (count_le + 1) / (_N_PERM + 1)

    # ── Pure-Python fallback (no numpy) ─────────────────────────────────────
    pool  = pool_rows[:]
    rng_p = random.Random(42)
    observed_deg_names = []
    for fn in fnames:
        tv = [r[fn] for r in task_rows if fn in r]
        bv = [r[fn] for r in baseline_rows if fn in r]
        if _series_is_near_constant(tv) or _series_is_near_constant(bv):
            observed_deg_names.append(fn)
    if observed_deg_names:
        _debug_log(
            "DEGENERATE",
            f"SumP {context}: skipping {len(observed_deg_names)}/{len(fnames)} near-constant features -> {_feature_sample(observed_deg_names)}",
        )

    def _compute_sum_p_slow(t_rows, b_rows):
        s = 0.0
        for fn in fnames:
            tv = [r[fn] for r in t_rows if fn in r]
            bv = [r[fn] for r in b_rows if fn in r]
            _, p = _welch_t(tv, bv)
            s += p
        return s

    obs_sum  = _compute_sum_p_slow(task_rows, baseline_rows)
    count_le = 0
    for _ in range(_N_PERM):
        rng_p.shuffle(pool)
        if _compute_sum_p_slow(pool[:n_task], pool[n_task:]) <= obs_sum:
            count_le += 1
    return obs_sum, (count_le + 1) / (_N_PERM + 1)


def _expected_direction(task_name: str, feature: str) -> Optional[str]:
    """Return only protocol-supported directional candidates.

    The optimization document often says *modulation* without fixing a
    direction. Those pairs intentionally return ``None`` instead of inheriting
    hypotheses from the retired battery.
    """
    raw_task = (task_name or "").lower()
    t = resolve_canonical_task(raw_task) or raw_task
    f = feature.lower()
    theta_up_tasks = {
        "adaptive_numerical_reasoning",
        "working_memory_manipulation",
        "semantic_induction_category_switching",
        "dual_task_rule_switching",
        "rule_based_anomaly_detection",
        "rapid_visual_comparison",
        "pattern_closure_visual_noise",
        "written_comprehension_synthesis",
    }
    occipital_alpha_suppression_tasks = {
        "visuospatial_transformation_orientation",
        "rule_based_anomaly_detection",
        "rapid_visual_comparison",
        "pattern_closure_visual_noise",
        "written_comprehension_synthesis",
    }
    if t in theta_up_tasks and f.startswith("theta_"):
        return "up"
    if t in occipital_alpha_suppression_tasks and f.startswith("alpha_"):
        return "down"
    return None


def _evaluate_expectation_alignment(task_name: str, feat_data: Dict[str, Any]) -> Dict[str, Any]:
    """Stateless port of EnhancedFeatureAnalysisEngine._evaluate_expectation_alignment.

    Requires feat_data entries to already contain 'significant_change', 'effect_size_d',
    'percent_change', 'delta', 'decision_flags' (call after the FDR / significance pass).
    """
    raw_task = (task_name or "").lower()
    t = resolve_canonical_task(raw_task) or raw_task
    thr = {"alpha": 0.25, "beta": 0.35, "gamma": 0.30, "theta": 0.30, "pct": 5.0}

    passed_features: List[Dict] = []
    key_dir_counts = {"with": 0, "against": 0}

    for feat, entry in feat_data.items():
        exp = _expected_direction(task_name, feat)
        if exp is None:
            continue
        delta  = float(entry.get("delta", 0.0))
        dir_ok = (delta > 0 and exp == "up") or (delta < 0 and exp == "down")
        key_dir_counts["with" if dir_ok else "against"] += 1

        if entry.get("significant_change"):
            flags = entry.get("decision_flags", {})
            p_dir = flags.get("p_one_sided")
            d_val = entry.get("effect_size_d")
            pct   = entry.get("percent_change")
            rule  = flags.get("pass_rule", "unknown")

            feat_thr_d = 0.25
            if   "alpha" in feat: feat_thr_d = thr["alpha"]
            elif "beta"  in feat: feat_thr_d = thr["beta"]
            elif "gamma" in feat: feat_thr_d = thr["gamma"]
            elif "theta" in feat: feat_thr_d = thr["theta"]

            d_meets   = d_val is not None and abs(d_val) >= feat_thr_d
            pct_meets = pct   is not None and abs(pct)   >= thr["pct"]
            passed_features.append({
                "feature": feat, "direction": exp,
                "p_dir": p_dir, "d": d_val, "pct": pct, "rule": rule,
                "d_meets_thr": d_meets, "pct_meets_thr": pct_meets,
            })

    # ── Task-specific grading (matching legacy rules) ──────────────────────────
    def _fp(feat_name: str, direction: str) -> bool:
        return any(f["feature"] == feat_name and f["direction"] == direction
                   and f.get("d_meets_thr") for f in passed_features)

    def _fps(prefix: str, direction: str) -> bool:
        return any(f["feature"].startswith(prefix) and f["direction"] == direction
                   and f.get("d_meets_thr") for f in passed_features)

    main_pass = False
    notes: List[str] = []
    key_features_map: Dict[str, List[str]] = {
        "adaptive_numerical_reasoning": ["theta_relative"],
        "working_memory_manipulation": ["theta_relative"],
        "semantic_induction_category_switching": ["theta_relative"],
        "visuospatial_transformation_orientation": ["alpha_relative", "theta_relative"],
        "dual_task_rule_switching": ["theta_relative"],
        "rule_based_anomaly_detection": ["theta_relative", "alpha_relative"],
        "rapid_visual_comparison": ["alpha_relative", "theta_relative"],
        "pattern_closure_visual_noise": ["alpha_relative", "theta_relative"],
        "written_comprehension_synthesis": ["alpha_relative", "theta_relative"],
    }
    key_features = key_features_map.get(t, [])
    if key_features:
        passed_names = {item["feature"] for item in passed_features}
        required = min(2, len(key_features))
        main_pass = sum(1 for name in key_features if name in passed_names) >= required
        notes.append(
            f"Continuous task-context signature: {sum(1 for name in key_features if name in passed_names)}/{len(key_features)} key features."
        )
    else:
        notes.append("No fixed directional signature; report modulation descriptively.")

    n_pass = len(passed_features)
    grade  = "D"
    if main_pass and n_pass >= 3: grade = "A"
    elif main_pass:               grade = "B"
    elif n_pass >= 2:             grade = "C"

    total_dir = key_dir_counts["with"] + key_dir_counts["against"]
    counter   = total_dir >= 3 and (key_dir_counts["against"] / float(total_dir)) >= 0.70

    drivers = sorted(
        [{"feature": f["feature"], "d": abs(f.get("d") or 0.0)} for f in passed_features],
        key=lambda x: x["d"], reverse=True,
    )[:3]

    # ── Insufficient-metrics check (port of legacy key-feature check) ──────────
    key_feats = key_features_map.get(t, [])
    missing_metrics: List[str] = []
    for kf in key_feats:
        entry = feat_data.get(kf, {})
        d_val = entry.get("effect_size_d")
        p_dir = entry.get("decision_flags", {}).get("p_one_sided")
        if d_val is None or p_dir is None:
            missing_metrics.append(kf)
    insufficient_metrics = len(missing_metrics) > 0
    if missing_metrics:
        notes.append(f"Insufficient metrics: {', '.join(missing_metrics)}")

    return {
        "grade":                grade,
        "passes":               passed_features,
        "top_drivers":          drivers,
        "counter_directional":  counter,
        "notes":                notes,
        "insufficient_metrics": insufficient_metrics,
    }


def _d_threshold(fname: str) -> float:
    """Band-specific Cohen's d threshold (matches legacy heuristics)."""
    if "Alpha" in fname or "alpha" in fname:
        return 0.25
    if "Beta" in fname or "beta" in fname:
        return 0.35
    return 0.30


def _pct_threshold(fname: str) -> float:
    """Feature-type-specific percent-change threshold.
    Mirrors legacy _thresholds_for_feature: 5% for relative/ratio features,
    10% for raw absolute features.
    """
    f = fname.lower()
    if f.endswith("_relative") or "ratio" in f:
        return _MIN_PERCENT_CHANGE_REL
    return _MIN_PERCENT_CHANGE


def _select_inference_feature_names(feature_names: List[str]) -> List[str]:
    names = [name for name in feature_names if not str(name).startswith("_")]
    name_set = set(names)
    selected: List[str] = []
    for name in names:
        if "_peak_" in str(name).lower():
            continue
        if name.endswith("_power_raw") and f"{name[:-10]}_power" in name_set:
            continue
        selected.append(name)
    return selected


_CONTINUOUS_BANDS = ("delta", "theta", "alpha", "beta", "gamma")
_CONTINUOUS_RATIOS = (
    "alpha_theta_ratio",
    "beta_alpha_ratio",
    "beta2_beta1_ratio",
    "theta2_theta1_ratio",
)


def _continuous_feature_names(rows: List[Dict[str, Any]]) -> List[str]:
    """Return the compact, non-peak spectral set used for temporal summaries."""
    available = set().union(*(row.keys() for row in rows)) if rows else set()
    selected = [
        f"{band}_{suffix}"
        for band in _CONTINUOUS_BANDS
        for suffix in ("power", "relative", "entropy")
        if f"{band}_{suffix}" in available
    ]
    selected.extend(name for name in _CONTINUOUS_RATIOS if name in available)
    if rows and all(float(row.get("_gamma_evaluated", 1.0) or 0.0) <= 0.0 for row in rows):
        selected = [name for name in selected if not name.startswith("gamma_")]
    return selected


def _finite_number(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _window_times(row: Dict[str, Any], fallback_index: int) -> Tuple[float, float]:
    start = _finite_number(row.get("_window_start_seconds"))
    end = _finite_number(row.get("_window_end_seconds"))
    if start is None:
        start = float(fallback_index) * _WINDOW_STEP_SEC
    if end is None or end <= start:
        end = start + _WINDOW_DURATION_SEC
    return start, end


def _descriptive_feature_summary(
    rows: List[Dict[str, Any]],
    feature_names: Optional[List[str]] = None,
) -> Dict[str, Dict[str, Any]]:
    selected = feature_names if feature_names is not None else _continuous_feature_names(rows)
    summaries: Dict[str, Dict[str, Any]] = {}
    for feature_name in selected:
        timed_values: List[Tuple[float, float]] = []
        for fallback_index, row in enumerate(rows):
            value = _finite_number(row.get(feature_name))
            if value is None:
                continue
            start, end = _window_times(row, fallback_index)
            timed_values.append(((start + end) / 2.0, value))
        if not timed_values:
            continue
        values = [item[1] for item in timed_values]
        mean_value = sum(values) / len(values)
        variance = sum((value - mean_value) ** 2 for value in values) / len(values)
        slope_per_minute: Optional[float] = None
        if len(timed_values) >= 2:
            mean_time = sum(item[0] for item in timed_values) / len(timed_values)
            denominator = sum((item[0] - mean_time) ** 2 for item in timed_values)
            if denominator > 1e-12:
                slope_per_second = sum(
                    (item[0] - mean_time) * (item[1] - mean_value)
                    for item in timed_values
                ) / denominator
                slope_per_minute = slope_per_second * 60.0
        summaries[feature_name] = {
            "n_windows": len(values),
            "mean": round(mean_value, 8),
            "std": round(math.sqrt(max(0.0, variance)), 8),
            "slope_per_minute": (
                round(slope_per_minute, 8) if slope_per_minute is not None else None
            ),
        }
    return summaries


def _max_contiguous_row_seconds(rows: List[Dict[str, Any]]) -> float:
    """Measure clean coverage while respecting both QC gaps and transport runs."""
    if not rows:
        return 0.0
    indexed_rows = list(enumerate(rows))
    indexed_rows.sort(key=lambda item: _window_times(item[1], item[0])[0])
    max_duration = 0.0
    run_start: Optional[float] = None
    previous_start: Optional[float] = None
    run_end: Optional[float] = None
    previous_segment: Any = None
    tolerance = max(1e-6, _WINDOW_STEP_SEC * 0.05)

    for fallback_index, row in indexed_rows:
        start, end = _window_times(row, fallback_index)
        segment = row.get("_transport_segment_id", "legacy")
        continues = (
            run_start is not None
            and segment == previous_segment
            and previous_start is not None
            and start >= previous_start
            and (start - previous_start) <= (_WINDOW_STEP_SEC + tolerance)
        )
        if not continues:
            if run_start is not None and run_end is not None:
                max_duration = max(max_duration, run_end - run_start)
            run_start = start
            run_end = end
        else:
            run_end = max(float(run_end or end), end)
        previous_start = start
        previous_segment = segment

    if run_start is not None and run_end is not None:
        max_duration = max(max_duration, run_end - run_start)
    return max(0.0, max_duration)


def _phase_definitions(task_metadata: Any) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    metadata = task_metadata if isinstance(task_metadata, dict) else {}
    raw_phases = metadata.get("phases")
    if not isinstance(raw_phases, list):
        return [], []
    eligible: List[Dict[str, Any]] = []
    ignored: List[Dict[str, str]] = []
    for index, raw_phase in enumerate(raw_phases):
        phase = raw_phase if isinstance(raw_phase, dict) else {}
        phase_id = str(phase.get("phase_id", phase.get("id", f"phase_{index + 1}")))
        start_ms = _finite_number(phase.get("start_elapsed_ms"))
        end_ms = _finite_number(phase.get("end_elapsed_ms"))
        start_seconds = (
            start_ms / 1000.0 if start_ms is not None
            else _finite_number(phase.get("start_seconds", phase.get("start")))
        )
        end_seconds = (
            end_ms / 1000.0 if end_ms is not None
            else _finite_number(phase.get("end_seconds", phase.get("end")))
        )
        planned_ms = _finite_number(phase.get("planned_duration_ms"))
        planned_seconds = (
            planned_ms / 1000.0 if planned_ms is not None
            else _finite_number(phase.get("planned_duration_seconds", phase.get("duration")))
        )
        if planned_seconds is None and start_seconds is not None and end_seconds is not None:
            planned_seconds = end_seconds - start_seconds
        if (
            start_seconds is None
            or end_seconds is None
            or planned_seconds is None
            or end_seconds <= start_seconds
        ):
            ignored.append({"phase_id": phase_id, "reason": "invalid_phase_timing"})
            continue
        if planned_seconds < _MIN_CONTIGUOUS_CLEAN_SECONDS:
            ignored.append({"phase_id": phase_id, "reason": "planned_duration_below_20_seconds"})
            continue
        if (end_seconds - start_seconds) < _MIN_CONTIGUOUS_CLEAN_SECONDS:
            ignored.append({"phase_id": phase_id, "reason": "phase_interval_below_20_seconds"})
            continue
        eligible.append({
            "phase_id": phase_id,
            "label": str(phase.get("label", phase_id)),
            "start_seconds": float(start_seconds),
            "end_seconds": float(end_seconds),
            "planned_duration_seconds": float(planned_seconds),
        })
    eligible.sort(key=lambda item: (item["start_seconds"], item["end_seconds"]))
    return eligible, ignored


def _continuous_time_series_summary(
    rows: List[Dict[str, Any]],
    task_metadata: Any,
) -> Dict[str, Any]:
    """Build descriptive task-time and conservatively gated phase summaries."""
    selected_features = _continuous_feature_names(rows)
    starts_and_ends = [_window_times(row, index) for index, row in enumerate(rows)]
    phase_definitions, ignored_phases = _phase_definitions(task_metadata)
    phase_summaries: List[Dict[str, Any]] = []

    for phase in phase_definitions:
        phase_rows = []
        for fallback_index, row in enumerate(rows):
            start, end = _window_times(row, fallback_index)
            if start >= phase["start_seconds"] - 1e-9 and end <= phase["end_seconds"] + 1e-9:
                phase_rows.append(row)
        max_clean_seconds = _max_contiguous_row_seconds(phase_rows)
        phase_scorable = max_clean_seconds >= _MIN_CONTIGUOUS_CLEAN_SECONDS
        phase_summaries.append({
            **phase,
            "n_clean_windows": len(phase_rows),
            "max_contiguous_clean_seconds": round(max_clean_seconds, 3),
            "meets_contiguous_clean_minimum": phase_scorable,
            "features": (
                _descriptive_feature_summary(phase_rows, selected_features)
                if phase_scorable else {}
            ),
        })

    comparison: Dict[str, Any]
    if len(phase_summaries) < 2:
        comparison = {
            "status": "withheld",
            "reason": "fewer_than_two_eligible_planned_phases",
            "compared_phase_ids": [phase["phase_id"] for phase in phase_summaries],
            "features": {},
        }
    elif not all(phase["meets_contiguous_clean_minimum"] for phase in phase_summaries):
        comparison = {
            "status": "withheld",
            "reason": "one_or_more_phases_have_less_than_20_contiguous_clean_seconds",
            "compared_phase_ids": [phase["phase_id"] for phase in phase_summaries],
            "features": {},
        }
    else:
        first_phase = phase_summaries[0]
        last_phase = phase_summaries[-1]
        differences: Dict[str, Dict[str, float]] = {}
        for feature_name in selected_features:
            first_feature = first_phase["features"].get(feature_name)
            last_feature = last_phase["features"].get(feature_name)
            if not first_feature or not last_feature:
                continue
            first_mean = float(first_feature["mean"])
            last_mean = float(last_feature["mean"])
            differences[feature_name] = {
                "last_minus_first": round(last_mean - first_mean, 8),
                "symmetric_percent_change": round(
                    _symmetric_percent_change(last_mean, first_mean), 6
                ),
            }
        comparison = {
            "status": "available",
            "reason": None,
            "compared_phase_ids": [phase["phase_id"] for phase in phase_summaries],
            "contrast": f"{last_phase['phase_id']}_minus_{first_phase['phase_id']}",
            "features": differences,
        }

    duration_span = (
        max(end for _, end in starts_and_ends) - min(start for start, _ in starts_and_ends)
        if starts_and_ends else 0.0
    )
    return {
        "status": "descriptive_only",
        "method": {
            "window_seconds": _RAW_WINDOW_SECONDS,
            "window_overlap": _RAW_WINDOW_OVERLAP,
            "window_step_seconds": _WINDOW_STEP_SEC,
            "time_axis": "recording_elapsed_transport_aware",
            "event_locked_analysis": False,
            "erp_analysis": False,
            "peak_metrics_included": False,
        },
        "n_clean_windows": len(rows),
        "duration_span_seconds": round(max(0.0, duration_span), 3),
        "selected_features": selected_features,
        "features": _descriptive_feature_summary(rows, selected_features),
        "phases": phase_summaries,
        "ignored_phases": ignored_phases,
        "phase_comparison": comparison,
    }


def _continuous_reference_comparison(
    target_rows: List[Dict[str, Any]],
    reference_rows_by_task: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Describe Task 7 against its Task 2/3 single-task references.

    This is deliberately not a behavioural cost score or a new inferential
    gate. It preserves the protocol's three-reference context while validated
    dual-task/switch-cost definitions remain unavailable.
    """
    required = [
        "working_memory_manipulation",
        "auditory_target_counting",
    ]
    missing = [task_id for task_id in required if not reference_rows_by_task.get(task_id)]
    if not target_rows or missing:
        return {
            "status": "withheld",
            "reason": "missing_scorable_single_task_reference",
            "missing_reference_task_ids": missing,
            "method": "descriptive_non_event_locked",
            "comparisons": {},
        }

    target_features = set(_continuous_feature_names(target_rows))
    comparisons: Dict[str, Any] = {}
    for reference_task_id in required:
        reference_rows = reference_rows_by_task[reference_task_id]
        feature_names = sorted(
            target_features.intersection(_continuous_feature_names(reference_rows))
        )
        target_summary = _descriptive_feature_summary(target_rows, feature_names)
        reference_summary = _descriptive_feature_summary(reference_rows, feature_names)
        feature_differences: Dict[str, Dict[str, float]] = {}
        for feature_name in feature_names:
            target_feature = target_summary.get(feature_name)
            reference_feature = reference_summary.get(feature_name)
            if not target_feature or not reference_feature:
                continue
            target_mean = float(target_feature["mean"])
            reference_mean = float(reference_feature["mean"])
            feature_differences[feature_name] = {
                "dual_minus_reference": round(target_mean - reference_mean, 8),
                "symmetric_percent_change": round(
                    _symmetric_percent_change(target_mean, reference_mean), 6
                ),
            }
        comparisons[reference_task_id] = {
            "target_clean_window_count": len(target_rows),
            "reference_clean_window_count": len(reference_rows),
            "features": feature_differences,
        }

    return {
        "status": "available",
        "reason": None,
        "missing_reference_task_ids": [],
        "method": "descriptive_non_event_locked",
        "behavioral_cost_threshold_available": False,
        "comparisons": comparisons,
    }


def _is_gamma_feature(name: str) -> bool:
    normalized = str(name).replace("_", "").lower()
    return "gamma" in normalized


def _symmetric_percent_change(task_mean: float, baseline_mean: float) -> float:
    denom = abs(task_mean) + abs(baseline_mean)
    if denom <= 1e-12:
        return 0.0
    return max(-200.0, min(200.0, 200.0 * (task_mean - baseline_mean) / denom))


def _build_blocks(rows: List[Dict], windows_per_block: int = _WINDOWS_PER_BLOCK) -> List[Dict]:
    """Group consecutive feature-rows into non-overlapping blocks and compute
    per-block feature means.  Mirrors legacy _build_blocks / block aggregation.

    This is the key step that decorre lates temporally adjacent EEG windows
    before running Welch's t-test and permutation tests.

    Args:
        rows:              List of per-window feature dicts.
        windows_per_block: How many consecutive windows to average into one block.
                           Default _WINDOWS_PER_BLOCK = 8 (= 8 s between the
                           starts of adjacent 50%-overlapped windows).

    Returns:
        List of per-block mean dicts.  Length ≈ len(rows) // windows_per_block.
    """
    if not rows or windows_per_block < 1:
        return rows
    fnames = _select_inference_feature_names(list(rows[0].keys()))
    internal_summary_names = [
        name for name in rows[0].keys()
        if str(name).startswith("_")
        and name not in {
            "_transport_segment_id",
            "_window_start_sample_index",
            "_window_end_sample_index_exclusive",
            "_window_start_seconds",
            "_window_end_seconds",
        }
        and _finite_number(rows[0].get(name)) is not None
    ]
    aggregate_names = fnames + internal_summary_names
    runs: List[List[Dict]] = []
    current_run: List[Dict] = []
    current_segment: Any = None
    previous_start_seconds: Optional[float] = None
    timing_tolerance = max(1e-6, _WINDOW_STEP_SEC * 0.05)
    for row in rows:
        segment = row.get("_transport_segment_id", "legacy")
        current_start_seconds = _finite_number(row.get("_window_start_seconds"))
        has_timing_gap = (
            current_run
            and previous_start_seconds is not None
            and current_start_seconds is not None
            and abs(
                (current_start_seconds - previous_start_seconds) - _WINDOW_STEP_SEC
            ) > timing_tolerance
        )
        if current_run and (segment != current_segment or has_timing_gap):
            runs.append(current_run)
            current_run = []
        current_segment = segment
        current_run.append(row)
        previous_start_seconds = current_start_seconds
    if current_run:
        runs.append(current_run)

    blocks: List[Dict] = []
    for run in runs:
        for start in range(0, len(run) - windows_per_block + 1, windows_per_block):
            chunk = run[start: start + windows_per_block]
            block: Dict[str, float] = {}
            for f in aggregate_names:
                vals = [float(r.get(f, 0.0)) for r in chunk]
                block[f] = sum(vals) / len(vals)
            blocks.append(block)
    if blocks:
        return blocks
    # No transport run was long enough to aggregate. Raw windows remain
    # independent rows; they are not concatenated into a synthetic block.
    return rows

def _correlation_guard_factor(all_rows: List[Dict], features: List[str]) -> float:
    """Port of EnhancedBrainLinkAnalyzerWindow._correlation_guard_factor.

    Computes the Spearman-rank correlation matrix across features using
    all_rows, finds the effective feature count via eigenvalue decomposition,
    and returns eff/nominal clamped to [0.05, 1.0].
    Falls back to 1.0 when numpy is unavailable or features is empty.
    """
    if not features or not all_rows or not _NP_AVAILABLE:
        return 1.0
    nominal = float(len(features))
    try:
        # Build matrix: shape (n_features, n_samples)
        mat = _np.array(
            [[float(r.get(f, 0.0)) for r in all_rows] for f in features],
            dtype=float,
        )
        # Spearman rank  ≈ Pearson on ranked rows
        if mat.shape[0] < 2 or mat.shape[1] < 2:
            return 1.0
        ranked = _np.argsort(_np.argsort(mat, axis=1), axis=1).astype(float)
        corr   = _np.corrcoef(ranked)
        corr   = _np.nan_to_num(corr, nan=0.0, posinf=0.0, neginf=0.0)
        eigvals = _np.linalg.eigvalsh(corr)
        eff     = float(_np.sum(_np.clip(eigvals, 0.0, 1.0)))
        eff     = max(1.0, eff)
        return float(_np.clip(eff / nominal, 0.05, 1.0))
    except Exception:
        return 1.0


def _analyze_task_vs_baseline(task_rows: List[Dict], baseline_rows: List[Dict],
                               task_id: str = "",
                               windows_per_block: int = _WINDOWS_PER_BLOCK) -> tuple:
    """
    Full per-task analysis mirroring EnhancedFeatureAnalysisEngine output.
    Returns (summary_dict, analysis_per_feature_dict).

    windows_per_block controls block aggregation (default 8 at a 1 s step).
    Pass windows_per_block=1 to disable blocking (individual windows, NOT recommended
    for overlapping EEG windows — produces spuriously low p-values).
    """
    if not task_rows or not baseline_rows:
        return {}, {}

    fnames = _select_inference_feature_names(list(task_rows[0].keys()))

    # ── Gamma EMG guard: drop gamma features when consistently guarded in task ─
    gamma_guarded_all = all(r.get("_gamma_evaluated", 1.0) <= 0 for r in task_rows)
    if gamma_guarded_all:
        fnames = [f for f in fnames if not f.startswith("gamma_")]

    # ── Block aggregation: average consecutive windows → decorrelated blocks ───
    # This is the most important step for valid p-values.
    task_blocks     = _build_blocks(task_rows,     windows_per_block)
    baseline_blocks = _build_blocks(baseline_rows, windows_per_block)

    # ── Preserve all blocks; unequal-n tests handle task/baseline length gaps ─
    task_eq     = task_blocks
    baseline_eq = baseline_blocks
    ess_task    = len(task_eq)
    ess_base    = len(baseline_eq)

    # ── Correlation guard: shrink alpha by effective-feature-count ratio ───────
    guard_factor    = _correlation_guard_factor(baseline_eq, fnames)
    local_alpha     = max(1e-9, _ALPHA     * guard_factor)
    local_fdr_alpha = max(1e-9, _FDR_ALPHA * guard_factor)

    # ── Per-feature Welch's t + Cohen's d ─────────────────────────────────────
    raw_p:    List[float]       = []
    t_stats:  Dict[str, float]  = {}
    feat_data: Dict[str, Any]   = {}
    degenerate_features: List[str] = []
    for fname in fnames:
        tv = [r[fname] for r in task_eq     if fname in r]
        bv = [r[fname] for r in baseline_eq if fname in r]
        tm = sum(tv) / len(tv) if tv else 0.0
        bm = sum(bv) / len(bv) if bv else 0.0
        t_val, p = _welch_t(tv, bv)
        d        = _cohens_d_vals(tv, bv)
        pct      = _symmetric_percent_change(tm, bm)
        ratio    = tm / (abs(bm) + 1e-12)
        z        = (tm - bm) / ((sum((x - bm)**2 for x in bv) / max(len(bv)-1, 1))**0.5 + 1e-12) if len(bv) > 1 else 0.0
        # Std devs
        t_std = (sum((x - tm)**2 for x in tv) / max(len(tv)-1, 1))**0.5 if len(tv) > 1 else 0.0
        b_std = (sum((x - bm)**2 for x in bv) / max(len(bv)-1, 1))**0.5 if len(bv) > 1 else 0.0
        # Degenerate variance / near-constant groups are not inferentially stable.
        pooled = ((t_std**2 + b_std**2) / 2.0)**0.5
        degenerate = pooled <= _INFERENTIAL_ABS_TOL or _series_is_near_constant(tv) or _series_is_near_constant(bv)
        reason = "Degenerate variance (pooled ≈ 0)" if degenerate else None
        if degenerate:
            degenerate_features.append(fname)
        # Discretization bin edges: quantile edges of baseline effect samples (legacy default bins=5)
        _disc_bins: Optional[list] = None
        if _NP_AVAILABLE and len(bv) >= 2:
            try:
                _eff_s = _np.array(bv, dtype=float) - bm
                _edges = _np.quantile(_eff_s, _np.linspace(0.0, 1.0, 6))
                _edges = _np.unique(_edges)
                if len(_edges) <= 1:
                    _edges = _np.linspace(float(_eff_s.min()) - 1.0, float(_eff_s.max()) + 1.0, 6)
                if len(_edges) != 6:
                    _edges = _np.linspace(float(_edges[0]), float(_edges[-1]), 6)
                _disc_bins = [round(float(e), 8) for e in _edges]
            except Exception:
                _disc_bins = None
        raw_p.append(p)
        t_stats[fname] = t_val
        feat_data[fname] = {
            "p_value":              round(p,        6),
            "q_value":              None,
            "t_stat":               round(t_val,    6),
            "delta":                round(tm - bm,  4),
            "effect_measure":       round(tm - bm,  4),
            "effect_size_d":        round(d,         4),
            "percent_change":       round(pct,       4),
            "task_mean":            round(tm,        4),
            "task_std":             round(t_std,     4),
            "baseline_mean":        round(bm,        4),
            "baseline_std":         round(b_std,     4),
            "z_score":              round(z,          4),
            "baseline_task_ratio":  round(ratio,      4),
            "log2_ratio":           round(math.log2(abs(ratio) + 1e-12), 4),
            "n_blocks_task":        len(tv),
            "n_blocks_baseline":    len(bv),
            "discrete_index":       1 if tm > bm else -1,
            "discretization_bins":  _disc_bins,
            "significant_change":   False,
            "bin_sig":              0,
            "gamma_evaluated":      True,
            "reason":               reason,
            "percent_change_method": "symmetric",
            "decision_flags":       {},
        }

    analysis_label = task_id or "combined"
    if degenerate_features:
        _debug_log(
            "DEGENERATE",
            f"{analysis_label}: {len(degenerate_features)}/{len(fnames)} features marked near-constant before inference -> {_feature_sample(degenerate_features)}",
        )
    else:
        _debug_log(
            "DEGENERATE",
            f"{analysis_label}: 0/{len(fnames)} features marked near-constant before inference",
        )

    # ── BH FDR + one-sided p + decision flags ─────────────────────────────────
    q_vals    = _bh_fdr(raw_p)
    sig_count = 0
    for i, fname in enumerate(fnames):
        entry  = feat_data[fname]
        entry["q_value"] = round(q_vals[i], 6)
        t_val  = t_stats[fname]
        p_two  = raw_p[i]
        exp    = _expected_direction(task_id, fname)

        # One-sided p when a directional expectation exists (legacy section 6.4)
        if exp == "up":
            p_one  = p_two / 2.0 if t_val > 0 else 1.0 - p_two / 2.0
            dir_ok = entry["delta"] > 0
        elif exp == "down":
            p_one  = p_two / 2.0 if t_val < 0 else 1.0 - p_two / 2.0
            dir_ok = entry["delta"] < 0
        else:
            p_one  = p_two
            dir_ok = True

        d_abs   = abs(entry["effect_size_d"])
        d_thr   = _d_threshold(fname)
        pct_thr = _pct_threshold(fname)
        p_sig   = bool(p_one     <= local_alpha     and dir_ok)
        q_sig   = bool(q_vals[i] <= local_fdr_alpha)
        d_sig   = bool(d_abs     >= d_thr           and dir_ok)
        pct_sig = bool(abs(entry["percent_change"]) >= pct_thr          and dir_ok)

        pass_rule: Optional[str] = None
        sig = False
        # Neuroprofile evidence is now statistical-gate first. Effect-size and
        # percent-change flags remain traceability observations but no longer
        # make a feature significant by themselves.
        if q_sig:
            sig = True
            pass_rule = "q"

        entry["significant_change"] = sig
        entry["bin_sig"]             = 1 if sig else 0
        entry["expected_direction"] = exp
        entry["p_one_sided"] = round(p_one, 6)
        entry["decision_flags"] = {
            "p_one_sided":        round(p_one, 6),
            "p_pass":             p_sig,
            "q_pass":             q_sig,
            "effect_pass":        d_sig,
            "percent_pass":       pct_sig,
            "percent_change_method": entry.get("percent_change_method"),
            "bh_rejected":        bool(q_vals[i] <= local_fdr_alpha),
            "expected_direction": exp,
            "direction_ok":       dir_ok,
            "pass_rule":          pass_rule,
        }
        entry["thresholds"] = {
            "alpha":                    local_alpha,
            "fdr_alpha":                local_fdr_alpha,
            "min_effect_size":          d_thr,
            "min_percent_change":       pct_thr,
            "correlation_guard_factor": guard_factor,
        }
        if sig:
            sig_count += 1

    # ── Fisher combined + KM correlation correction ────────────────────────────
    montage_gamma_guard_active = any(
        "_primary_channel_agreement" in row or "_primary_region_confidence" in row
        for row in task_eq
    )
    if montage_gamma_guard_active:
        def _mean_row_value(rows: List[Dict], key: str) -> Optional[float]:
            values = []
            for row in rows:
                try:
                    value = float(row[key])
                except Exception:
                    continue
                if math.isfinite(value):
                    values.append(value)
            return (sum(values) / len(values)) if values else None

        gamma_clean = (_mean_row_value(task_eq, "_gamma_evaluated") or 0.0) >= 0.8
        primary_agreement = _mean_row_value(task_eq, "_primary_channel_agreement")
        primary_confidence = _mean_row_value(task_eq, "_primary_region_confidence") or 0.0
        agreement_ok = (
            primary_agreement is not None
            and primary_agreement >= max(0.5, _MIN_PRIMARY_REGION_AGREEMENT)
            and primary_confidence >= 0.75
        )
        non_gamma_support = any(
            not _is_gamma_feature(name) and bool(feat_data[name].get("significant_change"))
            for name in fnames
        )

        for name in fnames:
            if not _is_gamma_feature(name):
                continue
            entry = feat_data[name]
            guard = {
                "emg_guard_clean": gamma_clean,
                "regional_agreement_ok": agreement_ok,
                "primary_channel_agreement": (
                    round(primary_agreement, 4)
                    if primary_agreement is not None else None
                ),
                "primary_region_confidence": round(primary_confidence, 4),
                "non_gamma_support": non_gamma_support,
            }
            entry["decision_flags"]["gamma_sparse_montage_guard"] = guard
            if entry.get("significant_change") and not all(
                (gamma_clean, agreement_ok, non_gamma_support)
            ):
                entry["significant_change"] = False
                entry["bin_sig"] = 0
                entry["decision_flags"]["pass_rule"] = None
                reason = entry.get("reason")
                guard_reason = "Sparse montage gamma requires clean EMG/high-frequency guard, regional agreement, and non-gamma support"
                entry["reason"] = f"{reason}; {guard_reason}" if reason else guard_reason

    sig_count = sum(1 for entry in feat_data.values() if entry.get("significant_change"))

    raw_fisher_stat, _, _ = _fisher_combined(raw_p)
    all_rows = task_eq + baseline_eq
    km_stat, km_p, km_df, km_mean_r, km_df_ratio = _km_fisher(
        raw_fisher_stat, fnames, all_rows
    )

    # ── SumP permutation on all task and baseline blocks ─────
    sum_p_val, sump_perm_p = _sum_p_perm(task_eq, baseline_eq, analysis_label)

    # ── Composite score: sum of -log10(q when available, else p) ───────────────
    # Mirrors legacy: adjusted_values uses q_value if present, else p_value
    _bh_rejected_count = sum(1 for i in range(len(fnames)) if q_vals[i] <= local_fdr_alpha)
    composite_vals = [
        max(feat_data[f]["q_value"] if feat_data[f]["q_value"] is not None
            else feat_data[f]["p_value"], 1e-12)
        for f in fnames
    ]
    composite = float(sum(-math.log10(v) for v in composite_vals)) if composite_vals else 0.0
    effect_mean = (sum(abs(feat_data[f]["effect_size_d"]) for f in fnames) / len(fnames)
                   if fnames else 0.0)

    # ── Cosine similarity between baseline and task feature vectors ────────────
    cosine_sim = cosine_dist = cosine_p = None
    if _NP_AVAILABLE and fnames:
        try:
            base_vec = _np.array([feat_data[f]["baseline_mean"] for f in fnames], dtype=float)
            task_vec = _np.array([feat_data[f]["task_mean"]     for f in fnames], dtype=float)
            base_n   = base_vec / (_np.linalg.norm(base_vec) + 1e-12)
            task_n   = task_vec / (_np.linalg.norm(task_vec) + 1e-12)
            cosine_sim  = float(_np.dot(base_n, task_n))
            cosine_dist = float(1.0 - cosine_sim)
            # Permutation test: shuffle baseline vector, count times distance >= observed
            rng_c    = random.Random(42)
            base_lst = base_vec.tolist()
            exceed   = 0
            for _ in range(_N_PERM):
                shuf   = list(base_lst)
                rng_c.shuffle(shuf)
                shuf_n = _np.array(shuf) / (_np.linalg.norm(shuf) + 1e-12)
                if float(1.0 - _np.dot(task_n, shuf_n)) >= cosine_dist:
                    exceed += 1
            cosine_p = (exceed + 1) / (_N_PERM + 1)
        except Exception:
            pass

    # ── SumP approximate fallback (mirrors legacy sum_p_approx_flag) ───────────
    sum_p_approx = False
    if sum_p_val is not None and sump_perm_p is None:
        k_ = len(raw_p)
        if k_ > 0:
            z_ = (sum_p_val - k_ / 2.0) / (k_ / 12.0) ** 0.5
            sump_perm_p  = max(0.0, min(1.0, 0.5 * math.erfc(z_ / 2.0 ** 0.5)))
            sum_p_approx = True

    nom_feat_count = len(fnames)
    eff_feat_count = round(nom_feat_count * guard_factor, 2)

    summary = {
        "fisher": {
            "stat":        round(raw_fisher_stat, 4) if raw_fisher_stat is not None else None,
            "p_naive":     None,   # not separately computed; km_p is primary
            "km_stat":     round(km_stat,  4) if km_stat  is not None else None,
            "km_p":        round(km_p,     6) if km_p     is not None else None,
            "km_df":       round(km_df,    2) if km_df    is not None else None,
            "km_df_ratio": round(km_df_ratio, 7) if km_df_ratio is not None else None,
            "km_mean_r":   round(km_mean_r,   7) if km_mean_r   is not None else None,
            "k_features":  nom_feat_count,
            "significant": bool(km_p is not None and km_p < _ALPHA),
            "alpha":       local_alpha,
        },
        "sum_p": {
            "value":            round(sum_p_val,    4) if sum_p_val    is not None else None,
            "perm_p":           round(sump_perm_p,  6) if sump_perm_p  is not None else None,
            "significant":      bool(sump_perm_p is not None and sump_perm_p < local_alpha),
            "permutation_used": True,
            "approximate":      sum_p_approx,
            "metadata": {
                "ess_baseline":  ess_base,
                "ess_task":      ess_task,
                "n_blocks_used": min(ess_base, ess_task),
            },
        },
        "permutation": {
            "n_perm": _N_PERM,
            "seed":   42,
            "preset": "default",
        },
        "ess": {
            "block_seconds":      windows_per_block * _WINDOW_STEP_SEC,
            "windows_per_block":  windows_per_block,
            "baseline_blocks":    ess_base,
            "task_blocks":        ess_task,
        },
        "composite": {"score": round(composite, 4)},
        "effect_size_mean": round(effect_mean, 4),
        "cosine": {
            "similarity": round(cosine_sim,  6) if cosine_sim  is not None else None,
            "distance":   round(cosine_dist, 6) if cosine_dist is not None else None,
            "p_value":    round(cosine_p,    6) if cosine_p    is not None else None,
        },
        "feature_selection": {
            "alpha":                      local_alpha,
            "fdr_alpha":                  local_fdr_alpha,
            "sig_feature_count":          sig_count,
            "correlation_guard_active":   guard_factor < 1.0,
            "correlation_guard_factor":   round(guard_factor, 4),
            "effective_feature_count":    eff_feat_count,
            "nominal_feature_count":      nom_feat_count,
            "bh_rejections":              _bh_rejected_count,
            "min_effect_size":            0.30,
            "min_percent_change_raw":     _MIN_PERCENT_CHANGE,
            "min_percent_change_rel":     _MIN_PERCENT_CHANGE_REL,
            "sig_prop":                   round(sig_count / max(1, nom_feat_count), 4),
        },
        "expectation": _evaluate_expectation_alignment(task_id, feat_data) if task_id else None,
    }
    return summary, feat_data


def _holm_bonferroni(p_items: List[tuple], alpha: float = _ALPHA) -> Dict[str, Any]:
    valid = [(name, float(p)) for name, p in p_items if p is not None and math.isfinite(float(p))]
    valid.sort(key=lambda item: item[1])
    m = len(valid)
    adjusted_by_name: Dict[str, float] = {}
    rejected_by_name: Dict[str, bool] = {}
    running = 0.0
    gate_open = True

    for rank, (name, p_value) in enumerate(valid, start=1):
        adjusted = min(1.0, max(running, (m - rank + 1) * p_value))
        running = adjusted
        threshold = alpha / float(m - rank + 1)
        rejected = bool(gate_open and p_value <= threshold)
        if not rejected:
            gate_open = False
        adjusted_by_name[name] = adjusted
        rejected_by_name[name] = rejected

    records = []
    for name, p_value in p_items:
        adj = adjusted_by_name.get(name)
        records.append({
            "task": name,
            "p_value": round(float(p_value), 6) if p_value is not None and math.isfinite(float(p_value)) else None,
            "holm_p": round(adj, 6) if adj is not None else None,
            "rejected": bool(rejected_by_name.get(name, False)),
        })

    return {
        "method": "holm_bonferroni",
        "alpha": alpha,
        "tasks": [name for name, _ in p_items],
        "n_tests": m,
        "n_rejected": sum(1 for value in rejected_by_name.values() if value),
        "results": records,
    }


def _normalize_eye_state(value: Any) -> Optional[str]:
    token = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if token in {"eyes_closed", "closed", "ec"}:
        return "eyes_closed"
    if token in {"eyes_open", "open", "eo"}:
        return "eyes_open"
    return None


def _task_sidecar_value(
    mapping: Any,
    raw_task_id: str,
    canonical_task_id: str,
) -> Any:
    if not isinstance(mapping, dict):
        return None
    if canonical_task_id in mapping:
        return mapping[canonical_task_id]
    if raw_task_id in mapping:
        return mapping[raw_task_id]
    for candidate, value in mapping.items():
        if resolve_canonical_task(str(candidate)) == canonical_task_id:
            return value
    return None


def _task_sample_rate(task_metadata: Dict[str, Any], multichannel: bool) -> int:
    default = _RAW_EEG_FS if multichannel else _LEGACY_RAW_EEG_FS
    raw_value = task_metadata.get("sample_rate_hz", task_metadata.get("sample_rate"))
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return default
    return value if 32 <= value <= 4096 else default


def _metadata_clean_interval_ceiling(task_metadata: Dict[str, Any]) -> Optional[float]:
    """Return an external clean-duration ceiling, never an upward override."""
    candidates: List[float] = []
    for key in ("max_contiguous_clean_seconds", "clean_contiguous_seconds"):
        try:
            value = float(task_metadata.get(key))
        except (TypeError, ValueError):
            continue
        if math.isfinite(value) and value >= 0.0:
            candidates.append(value)

    intervals = task_metadata.get("clean_intervals")
    interval_durations: List[float] = []
    if isinstance(intervals, list):
        for interval in intervals:
            if isinstance(interval, dict):
                start = interval.get("start_seconds", interval.get("start"))
                end = interval.get("end_seconds", interval.get("end"))
            elif isinstance(interval, (list, tuple)) and len(interval) >= 2:
                start, end = interval[0], interval[1]
            else:
                continue
            try:
                duration = float(end) - float(start)
            except (TypeError, ValueError):
                continue
            if math.isfinite(duration) and duration >= 0.0:
                interval_durations.append(duration)
    if interval_durations:
        candidates.append(max(interval_durations))
    return min(candidates) if candidates else None


def _apply_metadata_qc_constraints(
    task_qc: Dict[str, Any],
    task_metadata: Dict[str, Any],
) -> Dict[str, Any]:
    constrained = dict(task_qc)
    computed = float(constrained.get("max_contiguous_clean_seconds", 0.0) or 0.0)
    external_ceiling = _metadata_clean_interval_ceiling(task_metadata)
    effective = min(computed, external_ceiling) if external_ceiling is not None else computed
    constrained["computed_max_contiguous_clean_seconds"] = round(computed, 3)
    constrained["metadata_max_contiguous_clean_seconds"] = (
        round(external_ceiling, 3) if external_ceiling is not None else None
    )
    constrained["max_contiguous_clean_seconds"] = round(effective, 3)
    constrained["meets_contiguous_clean_minimum"] = effective >= _MIN_CONTIGUOUS_CLEAN_SECONDS
    return constrained


_CONTINUOUS_TASK_CONTRACT_VERSION = "mindspeller_continuous_task_result_v1"
_AUDIO_MODALITY_REQUIREMENTS: Dict[str, Set[str]] = {
    "adaptive_numerical_reasoning": {"speech"},
    "working_memory_manipulation": {"speech"},
    "auditory_target_counting": {"tone"},
    "semantic_induction_category_switching": {"speech"},
    "dual_task_rule_switching": {"speech", "tone"},
    "speech_in_noise_comprehension": {"speech", "noise"},
}

_PROFILE_COMPONENT_METADATA_FIELDS = {
    "stimuli": "stimulus_pack_version",
    "audio": "audio_pack_version",
    "rubrics": "rubric_set_version",
    "thresholds": "threshold_set_version",
}


def _valid_nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _declared_duration_milliseconds(task_metadata: Dict[str, Any]) -> Optional[float]:
    raw_milliseconds = task_metadata.get("planned_recording_duration_ms")
    if raw_milliseconds is not None:
        if isinstance(raw_milliseconds, bool):
            return None
        try:
            value = float(raw_milliseconds)
        except (TypeError, ValueError):
            return None
        return value if math.isfinite(value) and value > 0 else None

    raw_seconds = task_metadata.get("planned_recording_duration_seconds")
    if raw_seconds is None:
        return None
    if isinstance(raw_seconds, bool):
        return None
    try:
        value = float(raw_seconds) * 1000.0
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value > 0 else None


def _protocol_profile_ref_invalid_reasons(
    reference: Any,
    protocol_profile: Dict[str, Any],
    *,
    prefix: str,
    canonical_task_id: Optional[str] = None,
) -> List[str]:
    if reference is None:
        return []
    if not isinstance(reference, dict):
        return [f"{prefix}_must_be_an_object"]

    reasons: List[str] = []
    identity_fields = ("contract_version", "profile_id", "profile_version")
    for field in identity_fields:
        declared = reference.get(field)
        if not isinstance(declared, str) or not declared.strip():
            reasons.append(f"{prefix}_{field}_missing_or_invalid")
        elif declared.strip() != protocol_profile.get(field):
            reasons.append(f"{prefix}_{field}_mismatch")

    declared_status = reference.get("validation_status")
    if declared_status is not None:
        normalized_status = normalize_protocol_validation_status(declared_status)
        if normalized_status is None:
            reasons.append(f"{prefix}_validation_status_invalid")
        elif normalized_status != protocol_profile.get("validation_status"):
            reasons.append(f"{prefix}_validation_status_mismatch")

    raw_component_versions = reference.get("component_versions")
    if raw_component_versions is not None and not isinstance(raw_component_versions, dict):
        reasons.append(f"{prefix}_component_versions_invalid")
        raw_component_versions = {}
    if isinstance(raw_component_versions, dict):
        profile_components = protocol_profile.get("components", {})
        for component_name in PROTOCOL_PROFILE_COMPONENTS:
            declared_version = raw_component_versions.get(component_name)
            if declared_version is None:
                reasons.append(f"{prefix}_{component_name}_version_missing")
                continue
            expected_version = (
                profile_components.get(component_name, {}).get("version")
                if isinstance(profile_components.get(component_name), dict)
                else None
            )
            if declared_version != expected_version:
                reasons.append(f"{prefix}_{component_name}_version_mismatch")

    raw_component_refs = reference.get(
        "components", reference.get("component_refs")
    )
    if raw_component_refs is not None and not isinstance(raw_component_refs, dict):
        reasons.append(f"{prefix}_components_invalid")
        raw_component_refs = {}
    if isinstance(raw_component_refs, dict):
        profile_components = protocol_profile.get("components", {})
        for component_name in PROTOCOL_PROFILE_COMPONENTS:
            declared_component = raw_component_refs.get(component_name)
            expected_component = profile_components.get(component_name)
            if not isinstance(declared_component, dict):
                reasons.append(f"{prefix}_{component_name}_ref_missing_or_invalid")
                continue
            if not isinstance(expected_component, dict):
                reasons.append(f"{prefix}_{component_name}_profile_component_missing")
                continue
            for field in ("id", "version"):
                if declared_component.get(field) != expected_component.get(field):
                    reasons.append(f"{prefix}_{component_name}_{field}_mismatch")
            declared_component_status = declared_component.get("validation_status")
            if declared_component_status is not None:
                if (
                    normalize_protocol_validation_status(declared_component_status)
                    != expected_component.get("validation_status")
                ):
                    reasons.append(
                        f"{prefix}_{component_name}_validation_status_mismatch"
                    )

    if (
        canonical_task_id is not None
        and raw_component_versions is None
        and raw_component_refs is None
    ):
        reasons.append(f"{prefix}_component_provenance_missing")

    if canonical_task_id is not None:
        declared_task_ids = [
            reference[field]
            for field in ("canonical_task_id", "task_id")
            if field in reference
        ]
        if any(
            resolve_canonical_task(str(declared_task_id)) != canonical_task_id
            for declared_task_id in declared_task_ids
        ):
            reasons.append(f"{prefix}_canonical_task_id_mismatch")
        declared_durations = [
            reference[field]
            for field in (
                "expected_recording_duration_seconds",
                "duration_seconds",
            )
            if field in reference
        ]
        expected_duration = protocol_profile.get(
            "task_durations_seconds", {}
        ).get(canonical_task_id)
        for declared_duration in declared_durations:
            if isinstance(declared_duration, bool):
                reasons.append(f"{prefix}_expected_duration_invalid")
            else:
                try:
                    duration_value = float(declared_duration)
                except (TypeError, ValueError):
                    reasons.append(f"{prefix}_expected_duration_invalid")
                else:
                    if (
                        not math.isfinite(duration_value)
                        or duration_value != expected_duration
                    ):
                        reasons.append(f"{prefix}_expected_duration_mismatch")
    return reasons


def _task_protocol_profile_invalid_reasons(
    task_id: str,
    task_metadata: Dict[str, Any],
    behavioral_evidence: Any,
    protocol_profile: Dict[str, Any],
) -> List[str]:
    """Validate task duration and resource/scoring provenance against a profile."""
    reference = task_metadata.get("protocol_profile_ref")
    if (
        task_metadata.get("contract_version") == _CONTINUOUS_TASK_CONTRACT_VERSION
        and reference is None
    ):
        reasons = ["task_protocol_profile_ref_missing"]
    else:
        reasons = []
    reasons = _protocol_profile_ref_invalid_reasons(
        reference,
        protocol_profile,
        prefix="task_protocol_profile_ref",
        canonical_task_id=task_id,
    ) + reasons

    profile_components = protocol_profile.get("components", {})
    for component_name, metadata_field in _PROFILE_COMPONENT_METADATA_FIELDS.items():
        declared_version = task_metadata.get(metadata_field)
        if declared_version is None:
            continue
        expected_component = profile_components.get(component_name)
        expected_version = (
            expected_component.get("version")
            if isinstance(expected_component, dict)
            else None
        )
        if declared_version != expected_version:
            reasons.append(f"task_{component_name}_version_mismatch")

    declared_status = task_metadata.get("protocol_validation_status")
    if declared_status is not None:
        normalized_status = normalize_protocol_validation_status(declared_status)
        if normalized_status is None:
            reasons.append("task_protocol_validation_status_invalid")
        elif normalized_status != protocol_profile.get("validation_status"):
            reasons.append("task_protocol_validation_status_mismatch")

    duration_was_declared = any(
        field in task_metadata
        for field in (
            "planned_recording_duration_ms",
            "planned_recording_duration_seconds",
        )
    )
    declared_duration_ms = _declared_duration_milliseconds(task_metadata)
    expected_duration_seconds = protocol_profile.get(
        "task_durations_seconds", {}
    ).get(task_id)
    if duration_was_declared and declared_duration_ms is None:
        reasons.append("task_planned_recording_duration_invalid")
    elif (
        declared_duration_ms is not None
        and isinstance(expected_duration_seconds, int)
        and not math.isclose(
            declared_duration_ms,
            expected_duration_seconds * 1000.0,
            rel_tol=0.0,
            abs_tol=0.5,
        )
    ):
        reasons.append("task_planned_recording_duration_profile_mismatch")

    if isinstance(behavioral_evidence, dict):
        reasons.extend(
            _protocol_profile_ref_invalid_reasons(
                behavioral_evidence.get("protocol_profile_ref"),
                protocol_profile,
                prefix="behavioral_protocol_profile_ref",
                canonical_task_id=task_id,
            )
        )
        for component_name in ("rubrics", "thresholds"):
            metadata_field = _PROFILE_COMPONENT_METADATA_FIELDS[component_name]
            declared_version = behavioral_evidence.get(metadata_field)
            if declared_version is None:
                continue
            expected_component = profile_components.get(component_name)
            expected_version = (
                expected_component.get("version")
                if isinstance(expected_component, dict)
                else None
            )
            if declared_version != expected_version:
                reasons.append(f"behavioral_{component_name}_version_mismatch")

        scoring_configuration = behavioral_evidence.get(
            "configuration", behavioral_evidence.get("scoring_configuration")
        )
        if scoring_configuration is not None and not isinstance(
            scoring_configuration, dict
        ):
            reasons.append("behavioral_scoring_configuration_invalid")
        elif isinstance(scoring_configuration, dict):
            for field in ("profile_id", "profile_version"):
                declared_value = scoring_configuration.get(field)
                if declared_value != protocol_profile.get(field):
                    reasons.append(f"behavioral_scoring_{field}_mismatch")
            configured_status = normalize_protocol_validation_status(
                scoring_configuration.get("validation_status")
            )
            if configured_status != protocol_profile.get("validation_status"):
                reasons.append("behavioral_scoring_validation_status_mismatch")
            for component_name, id_field, version_field in (
                ("rubrics", "rubric_set_id", "rubric_set_version"),
                ("thresholds", "threshold_set_id", "threshold_set_version"),
            ):
                expected_component = profile_components.get(component_name)
                if not isinstance(expected_component, dict):
                    reasons.append(
                        f"behavioral_scoring_{component_name}_profile_component_missing"
                    )
                    continue
                if scoring_configuration.get(id_field) != expected_component.get("id"):
                    reasons.append(f"behavioral_scoring_{component_name}_id_mismatch")
                if (
                    scoring_configuration.get(version_field)
                    != expected_component.get("version")
                ):
                    reasons.append(
                        f"behavioral_scoring_{component_name}_version_mismatch"
                    )

    return list(dict.fromkeys(reasons))


def _task_audio_protocol_invalid_reasons(
    task_id: str,
    task_metadata: Dict[str, Any],
) -> List[str]:
    """Validate delivery metadata independently of the renderer's top-level flag."""
    recording = task_metadata.get("recording")
    audio_delivery = (
        recording.get("audio_delivery")
        if isinstance(recording, dict)
        else None
    )

    # Preserve explicit invalidation for legacy callers while requiring the
    # complete audit contract only for optimized-battery recordings.
    if task_metadata.get("contract_version") != _CONTINUOUS_TASK_CONTRACT_VERSION:
        if task_metadata.get("protocol_valid") is not False:
            return []
        if isinstance(audio_delivery, dict) and audio_delivery.get("protocol_complete") is False:
            return ["task_audio_delivery_incomplete"]
        return ["task_metadata_protocol_invalid"]

    reasons: List[str] = []
    if task_metadata.get("protocol_valid") is not True:
        reasons.append("task_protocol_validation_missing_or_invalid")
    if not isinstance(audio_delivery, dict):
        reasons.append("task_audio_delivery_audit_missing")
        return reasons

    count_fields = (
        "expected_speech_count",
        "scheduled_speech_count",
        "started_speech_count",
        "ended_speech_count",
        "expected_tone_count",
        "scheduled_tone_count",
        "started_tone_count",
        "ended_tone_count",
    )
    if not all(_valid_nonnegative_int(audio_delivery.get(field)) for field in count_fields):
        reasons.append("task_audio_delivery_audit_invalid")
    else:
        started_speech = audio_delivery["started_speech_count"]
        ended_speech = audio_delivery["ended_speech_count"]
        # A spoken stimulus that starts in the block's final seconds may not fire
        # its end event before the block finalizes and audio is cancelled; its
        # audio still played. The renderer discloses these in speech_end_waived_keys.
        # Count them as delivered so the audit is not failed for an unobservable
        # end event. The cap at started_speech keeps the waiver from ever excusing
        # a stimulus that never started.
        waived_keys = audio_delivery.get("speech_end_waived_keys")
        waived_count = len(waived_keys) if isinstance(waived_keys, list) else 0
        effective_ended_speech = min(started_speech, ended_speech + waived_count)
        speech_counts = [
            audio_delivery["expected_speech_count"],
            audio_delivery["scheduled_speech_count"],
            started_speech,
            effective_ended_speech,
        ]
        tone_counts = [
            audio_delivery[field]
            for field in (
                "expected_tone_count",
                "scheduled_tone_count",
                "started_tone_count",
                "ended_tone_count",
            )
        ]
        if len(set(speech_counts)) != 1 or len(set(tone_counts)) != 1:
            reasons.append("task_audio_delivery_incomplete")

        required = _AUDIO_MODALITY_REQUIREMENTS.get(task_id, set())
        if "speech" in required and speech_counts[0] <= 0:
            reasons.append("task_required_speech_audit_missing")
        if "tone" in required and tone_counts[0] <= 0:
            reasons.append("task_required_tone_audit_missing")

    incomplete_lists = (
        audio_delivery.get("incomplete_speech_keys"),
        audio_delivery.get("incomplete_tone_keys"),
        audio_delivery.get("failed_audio_keys"),
    )
    if any(not isinstance(values, list) or values for values in incomplete_lists):
        reasons.append("task_audio_delivery_incomplete")
    if audio_delivery.get("protocol_complete") is not True:
        reasons.append("task_audio_delivery_incomplete")

    required = _AUDIO_MODALITY_REQUIREMENTS.get(task_id, set())
    noise_required = audio_delivery.get("background_noise_required")
    noise_started = audio_delivery.get("background_noise_started")
    if not isinstance(noise_required, bool) or not isinstance(noise_started, bool):
        reasons.append("task_audio_delivery_audit_invalid")
    elif "noise" in required and not (noise_required and noise_started):
        reasons.append("task_required_noise_audit_missing")

    return list(dict.fromkeys(reasons))


@app.post("/analyze")
def analyze(body: Dict) -> Dict:
    """
    Analyse EEG task data vs baseline.

    Request:
      { "baseline": { "eyes_closed": [...], "eyes_open": [...] },
        "baseline_metadata": {
          "eyes_closed": {"transport_segments": [...]},
          "eyes_open": {"transport_segments": [...]}
        },
        "tasks":    { "<task_id>": [...], ... },
        "task_metadata": {
          "<task_id>": {"recording": {"transport_segments": [...]}, ...}
        },
        "protocol_profile": {
          "contract_version": "mindspeller_protocol_profile_v1",
          "profile_id": "...", "profile_version": "...",
          "validation_status": "candidate|pilot|validated",
          "components": {"stimuli": {...}, "audio": {...},
                         "rubrics": {...}, "thresholds": {...}},
          "task_durations_seconds": {"<canonical_task_id>": 90, ...}
        },
        "behavioral_evidence": { "<task_id>": {"status": "passed"}, ... },
        "block_seconds": 8.0   # optional; default 8.0 s per block
      }

    Response mirrors EnhancedFeatureAnalysisEngine.multi_task_results structure.
    """
    request_start = time.monotonic()
    baseline_raw: Dict[str, List] = body.get("baseline", {}) if isinstance(body.get("baseline", {}), dict) else {}
    baseline_metadata_raw = (
        body.get("baseline_metadata", {})
        if isinstance(body.get("baseline_metadata", {}), dict)
        else {}
    )
    tasks_raw:    Dict[str, List] = body.get("tasks", {}) if isinstance(body.get("tasks", {}), dict) else {}
    task_metadata_raw = body.get("task_metadata", {})
    behavioral_evidence_raw = body.get("behavioral_evidence", {})
    protocol_profile, protocol_profile_errors = normalize_protocol_profile(
        body.get("protocol_profile"),
        declaration_source=(
            "analysis_request" if "protocol_profile" in body
            else "backend_candidate_default"
        ),
    )
    if protocol_profile_errors:
        return {
            "error": "Invalid protocol_profile",
            "protocol_profile": protocol_profile,
            "protocol_profile_validation": {
                "valid": False,
                "errors": protocol_profile_errors,
                "normative_interpretation_allowed": False,
            },
        }

    # Optional block_seconds override (default _BLOCK_SECONDS = 8.0)
    req_block_sec    = body.get("block_seconds", _BLOCK_SECONDS)
    try:
        req_block_sec = max(0.5, float(req_block_sec))
    except (TypeError, ValueError):
        req_block_sec = _BLOCK_SECONDS
    win_per_block = max(1, round(req_block_sec / _WINDOW_STEP_SEC))

    ec_value = baseline_raw.get("eyes_closed", baseline_raw.get("ec", []))
    eo_value = baseline_raw.get("eyes_open", baseline_raw.get("eo", []))
    ec_samples: List = list(ec_value or []) if isinstance(ec_value, list) else []
    eo_samples: List = list(eo_value or []) if isinstance(eo_value, list) else []
    ec_metadata_value = baseline_metadata_raw.get(
        "eyes_closed", baseline_metadata_raw.get("ec", {})
    )
    eo_metadata_value = baseline_metadata_raw.get(
        "eyes_open", baseline_metadata_raw.get("eo", {})
    )
    ec_metadata = dict(ec_metadata_value) if isinstance(ec_metadata_value, dict) else {}
    eo_metadata = dict(eo_metadata_value) if isinstance(eo_metadata_value, dict) else {}

    if not ec_samples and not eo_samples:
        return {"error": "No baseline data provided"}

    normalized_tasks: List[Dict[str, Any]] = []
    seen_canonical: Set[str] = set()
    for raw_task_id, raw_samples in tasks_raw.items():
        raw_label = str(raw_task_id)
        canonical_task_id = resolve_canonical_task(raw_label) or raw_label.strip().lower()
        if canonical_task_id in seen_canonical:
            return {
                "error": (
                    f"Multiple task labels resolve to '{canonical_task_id}'. "
                    "Submit one uninterrupted block per canonical task."
                )
            }
        seen_canonical.add(canonical_task_id)
        metadata_value = _task_sidecar_value(task_metadata_raw, raw_label, canonical_task_id)
        metadata = dict(metadata_value) if isinstance(metadata_value, dict) else {}
        behavioral_evidence = _task_sidecar_value(
            behavioral_evidence_raw, raw_label, canonical_task_id
        )
        if behavioral_evidence is None:
            behavioral_evidence = metadata.get("behavioral_evidence")
        normalized_tasks.append({
            "canonical_task_id": canonical_task_id,
            "raw_task_id": raw_label,
            "samples": list(raw_samples or []) if isinstance(raw_samples, list) else [],
            "task_metadata": metadata,
            "behavioral_evidence": behavioral_evidence,
            "recognized": canonical_task_id in TASK_BASELINE_CONDITIONS,
        })

    # Record raw counts before conversion (for report header)
    ec_raw_count = len(ec_samples)
    eo_raw_count = len(eo_samples)
    task_counts = {
        str(task_id): len(samples if isinstance(samples, list) else [])
        for task in normalized_tasks
        for task_id, samples in [(task["canonical_task_id"], task["samples"])]
    }
    _eeg_log(
        "Analyze",
        f"request ec={ec_raw_count} eo={eo_raw_count} ec_shape={_raw_sample_shape(ec_samples)} "
        f"eo_shape={_raw_sample_shape(eo_samples)} tasks={task_counts}",
    )

    ec_multichannel = bool(_multichannel_raw_subset(ec_samples))
    eo_multichannel = bool(_multichannel_raw_subset(eo_samples))
    ec_rows, ec_qc, ec_montage = _feature_rows_for_transport_segments(
        ec_samples,
        ec_metadata,
        fs=_task_sample_rate(ec_metadata, multichannel=ec_multichannel),
    )
    eo_rows, eo_qc, eo_montage = _feature_rows_for_transport_segments(
        eo_samples,
        eo_metadata,
        fs=_task_sample_rate(eo_metadata, multichannel=eo_multichannel),
    )
    baseline_qc = _merge_qc_counters(ec_qc, eo_qc)
    baseline_rows = list(ec_rows) + list(eo_rows)
    baseline_montage = _merge_montage_summaries(
        [item for item in (ec_montage, eo_montage) if item]
    )
    _eeg_log(
        "Analyze",
        f"baseline_features rows={len(baseline_rows)} qc={baseline_qc} "
        f"ec_rows={len(ec_rows)} eo_rows={len(eo_rows)} montage={bool(baseline_montage)}",
    )

    per_task:      Dict[str, Any] = {}
    per_task_rows: Dict[str, List[Dict]] = {}
    all_task_rows: List[Dict]     = []
    montage_summaries: List[Dict[str, Any]] = [baseline_montage] if baseline_montage else []
    # A session-level baseline condition is one recording shared by every task
    # that matches its eye state. Analyse it once per condition so the pooled
    # comparison cannot count the same baseline windows once per task.
    matched_baseline_cache: Dict[str, Tuple[List[Dict], Dict[str, Any], Dict[str, Any]]] = {}
    scored_baseline_conditions: List[str] = []

    for task in normalized_tasks:
        task_id = task["canonical_task_id"]
        raw_task_id = task["raw_task_id"]
        samples = task["samples"]
        task_metadata = task["task_metadata"]
        behavioral_evidence = task["behavioral_evidence"]
        expected_baseline = task_baseline_condition(task_id)
        reported_eye_state = _normalize_eye_state(task_metadata.get("eye_state"))

        multichannel = bool(_multichannel_raw_subset(samples))
        task_fs = _task_sample_rate(task_metadata, multichannel=multichannel)
        task_rows, task_qc, task_montage = _feature_rows_for_transport_segments(
            samples,
            task_metadata,
            task_id=task_id,
            fs=task_fs,
        )
        task_qc = _apply_metadata_qc_constraints(task_qc, task_metadata)

        baseline_samples_for_task = (
            ec_samples if expected_baseline == "eyes_closed"
            else eo_samples if expected_baseline == "eyes_open"
            else []
        )
        comparison_baseline_metadata = (
            ec_metadata if expected_baseline == "eyes_closed"
            else eo_metadata if expected_baseline == "eyes_open"
            else {}
        )
        comparison_baseline_multichannel = bool(
            _multichannel_raw_subset(baseline_samples_for_task)
        )
        # Keyed by condition and montage profile: the region weighting depends on
        # the task, so tasks with different primary regions need their own rows.
        baseline_cache_key = (
            f"{expected_baseline}|{_montage_profile_for_task(task_id).get('primary_region', '')}"
        )
        if baseline_cache_key not in matched_baseline_cache:
            matched_baseline_cache[baseline_cache_key] = _feature_rows_for_transport_segments(
                baseline_samples_for_task,
                comparison_baseline_metadata,
                task_id=task_id,
                fs=_task_sample_rate(
                    comparison_baseline_metadata,
                    multichannel=comparison_baseline_multichannel,
                ),
            )
        comparison_baseline_rows, task_baseline_qc, task_baseline_montage = (
            matched_baseline_cache[baseline_cache_key]
        )

        invalid_reasons: List[str] = []
        if not task["recognized"]:
            invalid_reasons.append("unrecognized_non_core_task")
        if not samples:
            invalid_reasons.append("no_task_samples")
        if not task_qc.get("meets_contiguous_clean_minimum"):
            invalid_reasons.append("task_has_less_than_20_contiguous_clean_seconds")
        if not baseline_samples_for_task:
            invalid_reasons.append(f"missing_{expected_baseline or 'matched'}_baseline")
        elif not task_baseline_qc.get("meets_contiguous_clean_minimum"):
            invalid_reasons.append(
                f"{expected_baseline}_baseline_has_less_than_20_contiguous_clean_seconds"
            )
        invalid_reasons.extend(
            _task_audio_protocol_invalid_reasons(task_id, task_metadata)
        )
        invalid_reasons.extend(
            _task_protocol_profile_invalid_reasons(
                task_id,
                task_metadata,
                behavioral_evidence,
                protocol_profile,
            )
        )
        if reported_eye_state and expected_baseline and reported_eye_state != expected_baseline:
            invalid_reasons.append("task_eye_state_mismatch")

        scorable = not invalid_reasons
        if task_montage:
            montage_summaries.append(task_montage)
        if task_baseline_montage and not any(
            summary is task_baseline_montage for summary in montage_summaries
        ):
            montage_summaries.append(task_baseline_montage)
        _eeg_log(
            "AnalyzeTask",
            f"task={task_id} raw_label={raw_task_id} raw={len(samples)} shape={_raw_sample_shape(samples)} "
            f"feature_rows={len(task_rows)} baseline_rows={len(comparison_baseline_rows)} "
            f"baseline={expected_baseline} scorable={scorable} montage={bool(task_montage)}",
        )
        if scorable:
            summary, analysis = _analyze_task_vs_baseline(
                task_rows, comparison_baseline_rows, task_id, win_per_block
            )
            summary["validity"] = {"scorable": True, "invalid_reasons": []}
            per_task_rows[task_id] = task_rows
            all_task_rows.extend(task_rows)
            if baseline_cache_key not in scored_baseline_conditions:
                scored_baseline_conditions.append(baseline_cache_key)
            continuous_time_series = _continuous_time_series_summary(
                task_rows, task_metadata
            )
        else:
            summary, analysis = (
                {
                    "validity": {
                        "scorable": False,
                        "invalid_reasons": invalid_reasons,
                    }
                },
                {},
            )
            continuous_time_series = None
        per_task[task_id] = {
            "summary":      summary,
            "analysis":     analysis,
            "sample_count": len(task_rows),
            "raw_sample_count": len(samples),
            "canonical_task_id": task_id,
            "raw_task_labels": [raw_task_id],
            "baseline_condition": expected_baseline,
            "baseline_qc": task_baseline_qc,
            "task_qc": task_qc,
            "scorable": scorable,
            "invalid_reasons": invalid_reasons,
            "task_metadata": task_metadata,
            "protocol_profile": protocol_profile_reference(
                protocol_profile, task_id
            ),
            "behavioral_evidence": behavioral_evidence,
            "theoretical_onet_ability_candidates": theoretical_abilities_for_task(task_id),
        }
        if continuous_time_series is not None:
            per_task[task_id]["continuous_time_series"] = continuous_time_series
        if task_montage:
            per_task[task_id]["montage_evidence"] = task_montage

    dual_task_id = "dual_task_rule_switching"
    if dual_task_id in per_task:
        per_task[dual_task_id]["single_task_reference_comparison"] = (
            _continuous_reference_comparison(
                per_task_rows.get(dual_task_id, []),
                {
                    "working_memory_manipulation": per_task_rows.get(
                        "working_memory_manipulation", []
                    ),
                    "auditory_target_counting": per_task_rows.get(
                        "auditory_target_counting", []
                    ),
                },
            )
        )

    # Each matched baseline condition contributes its windows exactly once, so
    # pooling many eyes-closed tasks cannot restate one baseline as independent
    # observations and shrink the combined p-values.
    all_matched_baseline_rows: List[Dict] = []
    for cache_key in scored_baseline_conditions:
        all_matched_baseline_rows.extend(matched_baseline_cache[cache_key][0])

    # ── Combined (all tasks pooled vs baseline) ───────────────────────────────
    comb_summary, comb_analysis = ({}, {})
    if all_task_rows and all_matched_baseline_rows:
        comb_summary, comb_analysis = _analyze_task_vs_baseline(
            all_task_rows, all_matched_baseline_rows, windows_per_block=win_per_block
        )

    # ── Across-task omnibus (Kruskal-Wallis per feature + BH FDR) ─────────────
    n_sessions = len(per_task_rows)
    inference_baseline_rows = all_matched_baseline_rows or baseline_rows
    fnames = (
        _select_inference_feature_names(list(inference_baseline_rows[0].keys()))
        if inference_baseline_rows else []
    )

    # Gather per-feature value groups across tasks
    task_feat_groups: Dict[str, List[List[float]]] = {f: [] for f in fnames}
    for task_id, trows in per_task_rows.items():
        for fname in fnames:
            vals = [r[fname] for r in trows if fname in r]
            if vals:
                task_feat_groups[fname].append(vals)

    # Kruskal-Wallis per feature (requires ≥2 tasks with data)
    raw_omnibus_p: List[float]          = []
    raw_omnibus_stat: List[Optional[float]] = []
    for fname in fnames:
        groups = task_feat_groups[fname]
        if len(groups) >= 2 and _SCIPY_AVAILABLE:
            try:
                stat, p = _scipy_stats.kruskal(*groups)
                raw_omnibus_p.append(float(p))
                raw_omnibus_stat.append(float(stat))
            except Exception:
                raw_omnibus_p.append(1.0)
                raw_omnibus_stat.append(None)
        else:
            raw_omnibus_p.append(1.0)
            raw_omnibus_stat.append(None)

    omnibus_q_vals = _bh_fdr(raw_omnibus_p)

    feat_rankings: Dict[str, Any] = {}
    for i, fname in enumerate(fnames):
        ranking = []
        for tid, result in per_task.items():
            if not result.get("scorable"):
                continue
            d_abs = abs((result.get("analysis") or {}).get(fname, {}).get("effect_size_d") or 0)
            ranking.append({"task": tid, "median_effect": round(d_abs, 4)})
        ranking.sort(key=lambda r: r["median_effect"], reverse=True)
        stat = raw_omnibus_stat[i]
        p    = raw_omnibus_p[i]
        q    = omnibus_q_vals[i]
        feat_rankings[fname] = {
            "ranking":      ranking,
            "omnibus_stat": round(stat, 4) if stat is not None else None,
            "omnibus_p":    round(p,    6),
            "omnibus_q":    round(q,    6),
            "omnibus_sig":  bool(q <= _FDR_ALPHA and p <= _ALPHA),
        }

    n_omnibus_sig = sum(1 for f in feat_rankings.values() if f.get("omnibus_sig"))
    can_test = n_sessions >= 2 and _SCIPY_AVAILABLE
    task_p_items = [
        (task_id, ((result.get("summary") or {}).get("fisher") or {}).get("km_p"))
        for task_id, result in per_task.items()
        if result.get("scorable")
    ]
    cross_task_correction = _holm_bonferroni(task_p_items, _ALPHA)

    response = {
        "per_task": per_task,
        "combined": {
            "summary":  comb_summary,
            "analysis": comb_analysis,
        },
        "across_task": {
            "ranking_only":   not can_test,
            "sessions_used":  n_sessions,
            "n_significant":  n_omnibus_sig,
            "features":       feat_rankings,
            "cross_task_correction": cross_task_correction,
        },
        "baseline_kept":              baseline_qc["kept"],
        "ec_samples_raw":             ec_raw_count,
        "eo_samples_raw":             eo_raw_count,
        "baseline_rejected":          baseline_qc["rejected"],
        "baseline_rejected_not_worn": baseline_qc["not_worn"],
        "baseline_rejected_artifact": baseline_qc["artifact"],
        "baseline_rejected_flatline": baseline_qc["flatline"],
        "eo_windows":                 len(eo_rows),
        "baseline_qc_by_condition": {
            "eyes_closed": ec_qc,
            "eyes_open": eo_qc,
        },
        "baseline_metadata": {
            "eyes_closed": ec_metadata,
            "eyes_open": eo_metadata,
        },
        "task_metadata": {
            task_id: result.get("task_metadata", {})
            for task_id, result in per_task.items()
        },
        "behavioral_evidence": {
            task_id: result.get("behavioral_evidence")
            for task_id, result in per_task.items()
        },
        "protocol_profile": protocol_profile,
        "protocol_profile_validation": {
            "valid": True,
            "errors": [],
            "normative_interpretation_allowed": bool(
                protocol_profile.get("normative_interpretation_allowed")
            ),
        },
        "invalid_tasks": [
            task_id for task_id, result in per_task.items()
            if not result.get("scorable")
        ],
        "config": {
            "mode":                "aggregate_only",
            "alpha":               _ALPHA,
            "fdr_alpha":           _FDR_ALPHA,
            "dependence_correction": "none",
            "runtime_preset":      "default",
            "n_perm":              _N_PERM,
            "effect_measure":      "delta",
            "discretization_bins": 5,
            "window_seconds":      _RAW_WINDOW_SECONDS,
            "window_overlap":      _RAW_WINDOW_OVERLAP,
            "window_step_seconds": _WINDOW_STEP_SEC,
            "minimum_contiguous_clean_seconds": _MIN_CONTIGUOUS_CLEAN_SECONDS,
            "baseline_matching":   "task_eye_state",
            "transport_segmentation": "optional_zero_based_end_exclusive",
            "continuous_time_series": "descriptive_non_event_locked",
            "protocol_profile_contract_version": PROTOCOL_PROFILE_CONTRACT_VERSION,
            "task_recording_durations_seconds": dict(
                TASK_RECORDING_DURATIONS_SECONDS
            ),
        },
    }

    montage_summary = _merge_montage_summaries(montage_summaries)
    _eeg_log(
        "Analyze",
        f"complete tasks={len(per_task)} all_task_rows={len(all_task_rows)} "
        f"features={len(fnames)} montage={bool(montage_summary)} "
        f"elapsed_ms={round((time.monotonic() - request_start) * 1000, 1)}",
    )

    # ── Neuroprofile traceability export (additive, does not alter existing keys) ─
    try:
        response["neuroprofile_feature_export"] = build_neuroprofile_export(
            per_task, response
        )
        response["neuroprofile_feature_export"].update(
            _montage_export_fields(montage_summary)
        )
        export_keys = sorted(response["neuroprofile_feature_export"].keys())
        _eeg_log(
            "AnalyzeExport",
            f"neuroprofile_keys={export_keys[:12]}{'...' if len(export_keys) > 12 else ''}",
        )
    except Exception as _npe:
        _eeg_log("AnalyzeExport", f"failed: {_npe}")
        response["neuroprofile_feature_export"] = {
            "error": f"Neuroprofile export failed: {_npe}"
        }

    return response



# ─── WebSocket endpoint ───────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    _ws_clients.add(ws)
    _eeg_log("WebSocket", f"client connected clients={len(_ws_clients)}")
    # Immediately tell the new client the current connection state
    await ws.send_text(json.dumps({"type": "status", "value": _status}))
    # Also push the last known battery level so the UI doesn't wait for the next change
    if _battery_level is not None:
        await ws.send_text(json.dumps({"type": "battery", "level": _battery_level}))
    try:
        await _websocket_keepalive(ws)
    except WebSocketDisconnect:
        pass
    except RuntimeError:
        pass
    finally:
        _ws_clients.discard(ws)
        _eeg_log("WebSocket", f"client disconnected clients={len(_ws_clients)}")


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)
