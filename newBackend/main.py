import asyncio
import json
import math
import os
import sys
import random
import threading
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Set

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

# Add workspace root to sys.path so BrainLinkParser package can be found
_WORKSPACE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, _WORKSPACE_ROOT)

try:
    from BrainLinkParser.BrainLinkParser import BrainLinkParser as _BrainLinkParser
    _USE_SDK = True
    print("[Backend] Using BrainLinkParser SDK", flush=True)
except Exception as _e:
    _USE_SDK = False
    _BrainLinkParser = None
    print(f"[Backend] BrainLinkParser SDK unavailable ({_e}), falling back to TGAM parser", flush=True)

from eeg_processor import TGAMParser, create_eeg_filter
from neuroprofile_traceability import build_neuroprofile_export

# ─── Known BrainLink hardware identifiers ────────────────────────────────────
KNOWN_HWIDS  = ["5C361634682F", "5C3616327E59", "5C3616346938", "5C3616346838", "5C36163468D3", "5C3616327C21", "5C36163468D3", "90E2FC2C5F37", '90E2FC2C627C','90E2FC2C6378','90E2FC2C5E7D','90E2FC2C5FAA','90E2FC2C614B']
KNOWN_NAMES  = ["brainlink", "neurosky", "ftdi", "silabs", "ch340"]

# ─── Global connection state ──────────────────────────────────────────────────
_serial_port:   Optional[serial.Serial]   = None
_reader_thread: Optional[threading.Thread] = None
_stop_event:    threading.Event            = threading.Event()
_status:        str                        = "disconnected"
_battery_level: Optional[int]             = None    # last known battery % from 0x85 packet

# Asyncio queue bridging the serial-reader thread → WebSocket broadcaster
_broadcast_queue:  Optional[asyncio.Queue] = None
_broadcaster_task: Optional[asyncio.Task]  = None
_event_loop:       Optional[asyncio.AbstractEventLoop] = None

# Connected WebSocket clients
_ws_clients: Set[WebSocket] = set()


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

def _reader_worker(port_path: str) -> None:
    """
    Opens the serial port, feeds bytes into the TGAM parser, batches raw
    samples (~60 fps) and forwards all parsed data to the broadcast queue.
    """
    global _serial_port, _status

    eeg_filter = create_eeg_filter()
    raw_batch: List[int] = []
    last_flush = time.monotonic()
    last_data_time = time.monotonic()
    FLUSH_INTERVAL = 0.016
    SILENCE_TIMEOUT = 3.0

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
        # Band powers (attributes vary by firmware; use getattr with 0 default)
        bp_attrs = ['delta', 'theta', 'lowAlpha', 'highAlpha', 'lowBeta', 'highBeta', 'lowGamma', 'midGamma']
        bp = {k: getattr(data, k, 0) for k in bp_attrs}
        band_power = bp if any(bp.values()) else None
        print(f"[EEG] poorSignal={poor}  attention={attn}  meditation={med}", flush=True)
        _enqueue({
            "type":       "eeg_data",
            "poorSignal": poor,
            "attention":  attn,
            "meditation": med,
            "bandPower":  band_power,
            "battery":    _battery_level,
        })

    def _on_extend_eeg(data):
        global _battery_level
        bat = getattr(data, 'battery', None)
        if bat is not None:
            _battery_level = int(bat)
            print(f"[BATTERY] {_battery_level}%", flush=True)
            _enqueue({"type": "battery", "level": _battery_level})

    def _noop(*args): pass

    # ── SDK parser path ──────────────────────────────────────────────────────
    if _USE_SDK and _BrainLinkParser:
        sdk_parser = _BrainLinkParser(_on_eeg, _on_extend_eeg, _noop, _noop, _on_raw)

        try:
            _serial_port = serial.Serial(port_path, baudrate=115200, timeout=0.02)
            _status = "connected"
            _enqueue({"type": "status", "value": "connected"})

            while not _stop_event.is_set():
                chunk = _serial_port.read(64)
                if chunk:
                    last_data_time = time.monotonic()
                    sdk_parser.parse(chunk)

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
        global _battery_level
        data = TGAMParser.parse_payload(payload)

        if "raw" in data:
            raw_val = data["raw"]
            print(f"[RAW] {raw_val}", flush=True)
            _enqueue({"type": "raw_unfiltered_batch", "samples": [raw_val]})
            raw_batch.append(round(eeg_filter(raw_val)))

        now = time.monotonic()
        if now - last_flush >= FLUSH_INTERVAL and raw_batch:
            _enqueue({"type": "raw_batch", "samples": list(raw_batch)})
            raw_batch.clear()
            last_flush = now

        if "battery" in data:
            _battery_level = data["battery"]
            print(f"[BATTERY] {_battery_level}%", flush=True)
            _enqueue({"type": "battery", "level": _battery_level})

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
    """Return all available serial ports with metadata."""
    try:
        import serial.tools.list_ports  # ensure platform module is loaded
        ports = []
        for p in serial.tools.list_ports.comports():
            hwid = getattr(p, "hwid", "") or ""
            ports.append({
                "path":         p.device,
                "pnpId":        hwid,
                "manufacturer": p.manufacturer or "",
                "description":  p.description  or p.device,
            })
        return {"ports": ports}
    except Exception as exc:
        print(f"[Ports] list error: {exc}", flush=True)
        return {"ports": []}



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
    Open a serial connection to a BrainLink device.

    Request:  { "port": "COM3" }
    Response: { "success": true } | { "success": false, "error": "..." }
    """
    global _reader_thread, _status

    port_path = body.get("port", "").strip()
    if not port_path:
        return {"success": False, "error": "port is required"}

    # Disconnect existing connection first
    _stop_event.set()
    if _reader_thread and _reader_thread.is_alive():
        _reader_thread.join(timeout=2.0)
    _stop_event.clear()

    _status = "connecting"
    _enqueue({"type": "status", "value": "connecting"})

    _reader_thread = threading.Thread(
        target=_reader_worker,
        args=(port_path,),
        daemon=True,
        name="eeg-reader",
    )
    _reader_thread.start()

    return {"success": True}



@app.post("/disconnect")
def disconnect() -> Dict:
    """Close the active serial connection."""
    global _status
    _stop_event.set()
    if _reader_thread and _reader_thread.is_alive():
        _reader_thread.join(timeout=2.0)
    _stop_event.clear()
    _status = "disconnected"
    _enqueue({"type": "status", "value": "disconnected"})
    return {"success": True}


_BANDS = ["delta", "theta", "lowAlpha", "highAlpha", "lowBeta", "highBeta", "lowGamma", "midGamma"]

# Raw EEG conversion helpers used when the frontend sends raw 512 Hz samples
# instead of TGAM-chip band-power dicts.
_RAW_EEG_FS      = 512    # BrainLink sample rate (Hz)
_RAW_WINDOW      = 1024   # samples per FFT window (2.0 sec at 512 Hz)
_RAW_STEP        = 1024   # non-overlapping offline windows for block statistics
_MT_TAPERS       = 3      # DPSS multitaper count (matches legacy mt_tapers=3)
_MT_NW           = 2.5    # time-bandwidth product (matches legacy NW=2.5)

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
    if not _NP_AVAILABLE or len(raw_samples) < _RAW_WINDOW:
        return []

    arr    = _np.asarray(raw_samples, dtype=_np.float64)
    n      = len(arr)
    freqs  = _np.fft.rfftfreq(_RAW_WINDOW, d=1.0 / fs)   # (n_freqs,)

    # ── Build strided window matrix without copying data where possible ───────
    n_win = max(0, (n - _RAW_WINDOW) // _RAW_STEP + 1)
    if n_win == 0:
        return []
    idx        = (_np.arange(n_win)[:, None] * _RAW_STEP +
                  _np.arange(_RAW_WINDOW)[None, :])       # (n_win, _RAW_WINDOW)
    segs       = arr[idx]                                  # (n_win, _RAW_WINDOW)
    segs       = segs - segs.mean(axis=1, keepdims=True)  # DC removal per window

    # ── Multitaper PSD (all windows, all tapers in one batch FFT) ─────────────
    hann   = _np.hanning(_RAW_WINDOW)                     # fallback taper
    psd_batch = None                                       # (n_win, n_freqs)

    if _DPSS_AVAILABLE:
        try:
            tapers = _dpss(_RAW_WINDOW, NW=_MT_NW, Kmax=_MT_TAPERS, sym=False)
            # tapers: (K, _RAW_WINDOW)
            for k in range(_MT_TAPERS):
                tapered = segs * tapers[k]                # (n_win, _RAW_WINDOW)
                Xk = _np.fft.rfft(tapered, axis=1)       # (n_win, n_freqs)
                Pk = (_np.abs(Xk) ** 2) / (fs * _RAW_WINDOW + 1e-12)
                psd_batch = Pk if psd_batch is None else psd_batch + Pk
            psd_batch = psd_batch / float(_MT_TAPERS)
        except Exception:
            psd_batch = None

    if psd_batch is None:
        tapered   = segs * hann                           # (n_win, _RAW_WINDOW)
        Xk        = _np.fft.rfft(tapered, axis=1)        # (n_win, n_freqs)
        psd_batch = (_np.abs(Xk) ** 2) / (_RAW_WINDOW * fs + 1e-12)

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
    if not _NP_AVAILABLE or len(raw_samples) < _RAW_WINDOW:
        return []
    arr = _np.asarray(raw_samples, dtype=_np.float64)
    windows = []
    for start in range(0, len(arr) - _RAW_WINDOW + 1, _RAW_STEP):
        windows.append(arr[start:start + _RAW_WINDOW])
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
        neural_ratio = float(_np.sum(psd[(freqs >= 0.5) & (freqs <= 13.0)])) / total
        hf_ratio = float(_np.sum(psd[freqs >= 30.0])) / total
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


def _raw_to_feature_windows(raw_samples: List, fs: int = _RAW_EEG_FS) -> List[Dict[str, float]]:
    if not _NP_AVAILABLE:
        return []
    return [_raw_window_to_features(window, fs) for window in _iter_raw_windows(raw_samples, fs)]


def _baseline_feature_rows(samples: List) -> tuple:
    counters = {
        "kept": 0,
        "rejected": 0,
        "not_worn": 0,
        "artifact": 0,
        "flatline": 0,
    }
    if not samples:
        return [], counters
    if isinstance(samples[0], (int, float)):
        rows: List[Dict[str, float]] = []
        for window in _iter_raw_windows(samples):
            reason = _raw_window_qc(window)
            if reason is None:
                rows.append(_raw_window_to_features(window))
                counters["kept"] += 1
            else:
                counters["rejected"] += 1
                counters[reason] += 1
        return rows, counters

    rows = _extract_features(samples)
    counters["kept"] = len(rows)
    return rows, counters


def _samples_to_feature_rows(samples: List) -> List[Dict[str, float]]:
    if not samples:
        return []
    if isinstance(samples[0], (int, float)):
        return _raw_to_feature_windows(samples)
    return _extract_features(samples)


def _maybe_convert_raw(samples: List) -> List[Dict]:
    """If samples is a list of numbers (raw EEG), convert to raw feature windows.
    If already a list of dicts (band-power), return as-is."""
    if not samples:
        return samples
    if isinstance(samples[0], (int, float)):
        return _raw_to_feature_windows(samples)
    return samples
_ALPHA              = 0.05
_FDR_ALPHA          = 0.05
_N_PERM             = 1000
_MIN_PERCENT_CHANGE      = 10.0  # raw-power features
_MIN_PERCENT_CHANGE_REL  =  5.0  # relative/ratio features (bounded 0-1, smaller natural range)

# Block aggregation constants (mirrors legacy default block_seconds=8.0)
# Window duration = window_samples / fs = 1024 / 512 = 2.0s (raw EEG path)
# windows_per_block = 8.0 / 2.0 = 4 windows -> 8 seconds of EEG per block
_BLOCK_SECONDS       = 8.0
_WINDOW_DURATION_SEC = _RAW_WINDOW / _RAW_EEG_FS   # 2.0 s
_WINDOWS_PER_BLOCK   = max(1, round(_BLOCK_SECONDS / _WINDOW_DURATION_SEC))  # 4

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
    if _SCIPY_AVAILABLE:
        try:
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
    if fisher_stat is None or k <= 1 or not all_rows:
        return fisher_stat, None, float(2 * max(k, 1)), None, None

    # ── Build feature matrix (k × n) and compute full correlation matrix ──────
    if _NP_AVAILABLE:
        try:
            mat  = _np.array([[float(r.get(f, 0.0)) for r in all_rows]
                               for f in fnames], dtype=float)   # (k, n)
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


def _sum_p_perm(task_rows: List[Dict], baseline_rows: List[Dict]) -> tuple:
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

    if _NP_AVAILABLE:
        # ── Fast numpy path ──────────────────────────────────────────────────
        mat = _np.array([[float(r.get(f, 0.0)) for f in fnames]
                          for r in pool_rows], dtype=float)   # (n_total, n_feat)

        def _sum_p_vec(t_idx: "_np.ndarray", b_idx: "_np.ndarray") -> float:
            if _SCIPY_AVAILABLE:
                try:
                    _, p_arr = _scipy_stats.ttest_ind(
                        mat[t_idx], mat[b_idx], axis=0, equal_var=False)
                    p_arr = _np.where(_np.isfinite(p_arr), p_arr, 1.0)
                    return float(p_arr.sum())
                except Exception:
                    pass
            # Pure-numpy Welch fallback (approximate, avoids scipy import failure)
            a, b  = mat[t_idx], mat[b_idx]
            n1, n2 = a.shape[0], b.shape[0]
            m1, m2 = a.mean(0), b.mean(0)
            v1 = a.var(0, ddof=1);  v2 = b.var(0, ddof=1)
            se = _np.sqrt(v1 / n1 + v2 / n2) + 1e-12
            t_stat = _np.abs((m1 - m2) / se)
            # Estimate p via standard normal (over-estimates df but is fast)
            p_arr  = 2.0 * (1.0 - 0.5 * (1.0 + _np.vectorize(math.erf)(t_stat / math.sqrt(2))))
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
    """Port of EnhancedBrainLinkAnalyzerWindow._expected_direction.
    Returns 'up', 'down', or None (no expectation for this task/feature pair).
    """
    t = (task_name or "").lower()
    f = feature.lower()
    if t == "mental_math":
        if f.startswith("alpha_"):                                  return "down"
        if f.startswith("beta_") or "beta_alpha_ratio" in f:       return "up"
        if f.startswith("gamma_"):                                  return "up"
        if f == "alpha_theta_ratio":                                return "down"
    elif t == "visual_imagery":
        if f.startswith("alpha_"):                                  return "up"
        if f == "alpha_theta_ratio":                                return "up"
        if "beta_alpha_ratio" in f:                                 return "down"
    elif t == "working_memory":
        if f.startswith("theta_"):                                  return "up"
        if f.startswith("alpha_"):                                  return "down"
        if "beta_alpha_ratio" in f or f.startswith("beta_"):       return "up"
        if f.startswith("gamma_"):                                  return "up"
    elif t == "attention_focus":
        if f.startswith("alpha_"):                                  return "down"
        if f.startswith("beta_") or "beta_alpha_ratio" in f:       return "up"
        if f.startswith("theta_"):                                  return "down"
    elif t == "language_processing":
        if f.startswith("beta_") or "beta_alpha_ratio" in f:       return "up"
        if f.startswith("alpha_"):                                  return "down"
        if f.startswith("gamma_"):                                  return "up"
    elif t == "motor_imagery":
        if f.startswith("alpha_"):                                  return "down"
        if "beta_alpha_ratio" in f or f.startswith("beta_"):       return "up"
    elif t == "cognitive_load":
        if f.startswith("theta_"):                                  return "up"
        if f.startswith("alpha_"):                                  return "down"
        if f.startswith("beta_") or "beta_alpha_ratio" in f:       return "up"
    return None


def _evaluate_expectation_alignment(task_name: str, feat_data: Dict[str, Any]) -> Dict[str, Any]:
    """Stateless port of EnhancedFeatureAnalysisEngine._evaluate_expectation_alignment.

    Requires feat_data entries to already contain 'significant_change', 'effect_size_d',
    'percent_change', 'delta', 'decision_flags' (call after the FDR / significance pass).
    """
    t = (task_name or "").lower()
    task_thr: Dict[str, Dict[str, float]] = {
        "mental_math":         {"alpha": 0.25, "beta": 0.35, "gamma": 0.30, "theta": 0.30, "pct": 5.0},
        "attention_focus":     {"alpha": 0.25, "beta": 0.35, "gamma": 0.30, "theta": 0.30, "pct": 5.0},
        "visual_imagery":      {"alpha": 0.30, "beta": 0.30, "gamma": 0.30, "theta": 0.30, "pct": 8.0},
        "working_memory":      {"alpha": 0.25, "beta": 0.35, "gamma": 0.30, "theta": 0.30, "pct": 5.0},
        "cognitive_load":      {"alpha": 0.25, "beta": 0.30, "gamma": 0.30, "theta": 0.30, "pct": 5.0},
        "motor_imagery":       {"alpha": 0.25, "beta": 0.30, "gamma": 0.30, "theta": 0.30, "pct": 5.0},
        "language_processing": {"alpha": 0.25, "beta": 0.35, "gamma": 0.30, "theta": 0.30, "pct": 5.0},
    }
    thr = task_thr.get(t, {"alpha": 0.25, "beta": 0.30, "gamma": 0.30, "theta": 0.30, "pct": 5.0})

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
    try:
        if t == "mental_math":
            a_dn = _fp("alpha_relative", "down")
            b_up = _fp("beta_relative",  "up")
            r_up = _fp("beta_alpha_ratio", "up")
            g_up = _fp("gamma_relative", "up")
            if a_dn and (b_up or r_up) and g_up:
                main_pass = True; notes.append("All key features (α↓, β/ratio↑, γ↑) passed")
            elif a_dn and (b_up or r_up):
                main_pass = True; notes.append("Core features (α↓, β/ratio↑) passed")
            else:
                notes.append("Missing core mental_math features")
        elif t == "attention_focus":
            if _fp("alpha_relative", "down") and (_fp("beta_relative", "up") or _fp("beta_alpha_ratio", "up")):
                main_pass = True; notes.append("Core features (α↓, β/ratio↑) passed")
            else:
                notes.append("Missing core attention_focus features")
        elif t == "visual_imagery":
            main_pass = _fp("alpha_relative", "up") or _fp("alpha_theta_ratio", "up")
            notes.append("Visual imagery: alpha/ratio signature")
        elif t == "working_memory":
            main_pass = _fps("theta_", "up") and (_fp("alpha_relative", "down") or _fp("beta_alpha_ratio", "up"))
            notes.append("Working memory: theta + alpha/ratio")
        elif t == "cognitive_load":
            main_pass = _fps("theta_", "up") and _fp("alpha_relative", "down")
            notes.append("Cognitive load: theta↑ + alpha↓")
        elif t == "motor_imagery":
            main_pass = _fp("alpha_relative", "down") or _fp("beta_relative", "up") or _fp("beta_alpha_ratio", "up")
            notes.append("Motor imagery: alpha↓ or beta↑")
        elif t == "language_processing":
            main_pass = _fp("alpha_relative", "down") and _fp("beta_alpha_ratio", "up")
            notes.append("Language: alpha↓ + ratio↑")
    except Exception as exc:
        notes.append(f"Grading error: {exc}")

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
    _key_features_map: Dict[str, List[str]] = {
        "mental_math":         ["alpha_relative", "beta_relative", "beta_alpha_ratio", "gamma_relative"],
        "attention_focus":     ["alpha_relative", "beta_relative", "beta_alpha_ratio"],
        "visual_imagery":      ["alpha_relative", "alpha_theta_ratio"],
        "working_memory":      ["theta_relative", "alpha_relative", "beta_alpha_ratio"],
        "cognitive_load":      ["theta_relative", "alpha_relative"],
        "motor_imagery":       ["alpha_relative", "beta_relative", "beta_alpha_ratio"],
        "language_processing": ["alpha_relative", "beta_alpha_ratio"],
    }
    key_feats = _key_features_map.get(t, [])
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


def _build_blocks(rows: List[Dict], windows_per_block: int = _WINDOWS_PER_BLOCK) -> List[Dict]:
    """Group consecutive feature-rows into non-overlapping blocks and compute
    per-block feature means.  Mirrors legacy _build_blocks / block aggregation.

    This is the key step that decorre lates temporally adjacent EEG windows
    before running Welch's t-test and permutation tests.

    Args:
        rows:              List of per-window feature dicts.
        windows_per_block: How many consecutive windows to average into one block.
                           Default _WINDOWS_PER_BLOCK = 4 (= 8 s at 2.0 s/window).

    Returns:
        List of per-block mean dicts.  Length ≈ len(rows) // windows_per_block.
    """
    if not rows or windows_per_block < 1:
        return rows
    fnames = list(rows[0].keys())
    blocks: List[Dict] = []
    for start in range(0, len(rows) - windows_per_block + 1, windows_per_block):
        chunk = rows[start: start + windows_per_block]
        block: Dict[str, float] = {}
        for f in fnames:
            vals = [float(r.get(f, 0.0)) for r in chunk]
            block[f] = sum(vals) / len(vals)
        blocks.append(block)
    return blocks if blocks else rows   # fallback: return raw if too short for even one block

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

    windows_per_block controls block aggregation (default 4 = 8 s at 2.0 s/window).
    Pass windows_per_block=1 to disable blocking (individual windows, NOT recommended
    for overlapping EEG windows — produces spuriously low p-values).
    """
    if not task_rows or not baseline_rows:
        return {}, {}

    fnames = list(task_rows[0].keys())

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
    for fname in fnames:
        tv = [r[fname] for r in task_eq     if fname in r]
        bv = [r[fname] for r in baseline_eq if fname in r]
        tm = sum(tv) / len(tv) if tv else 0.0
        bm = sum(bv) / len(bv) if bv else 0.0
        t_val, p = _welch_t(tv, bv)
        d        = _cohens_d_vals(tv, bv)
        pct      = ((tm - bm) / (abs(bm) + 1e-12)) * 100.0
        ratio    = tm / (abs(bm) + 1e-12)
        z        = (tm - bm) / ((sum((x - bm)**2 for x in bv) / max(len(bv)-1, 1))**0.5 + 1e-12) if len(bv) > 1 else 0.0
        # Std devs
        t_std = (sum((x - tm)**2 for x in tv) / max(len(tv)-1, 1))**0.5 if len(tv) > 1 else 0.0
        b_std = (sum((x - bm)**2 for x in bv) / max(len(bv)-1, 1))**0.5 if len(bv) > 1 else 0.0
        # Degenerate variance (pooled ≈ 0)
        pooled = ((t_std**2 + b_std**2) / 2.0)**0.5
        degenerate = pooled <= 1e-12
        reason = "Degenerate variance (pooled ≈ 0)" if degenerate else None
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
            "decision_flags":       {},
        }

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
        # Legacy rule: p alone is sufficient (not p+q); effect and pct are fallbacks
        if p_sig:   sig = True; pass_rule = "p"
        elif d_sig: sig = True; pass_rule = "d"
        elif pct_sig: sig = True; pass_rule = "pct"

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
    raw_fisher_stat, _, _ = _fisher_combined(raw_p)
    all_rows = task_eq + baseline_eq
    km_stat, km_p, km_df, km_mean_r, km_df_ratio = _km_fisher(
        raw_fisher_stat, fnames, all_rows
    )

    # ── SumP permutation on all task and baseline blocks ─────
    sum_p_val, sump_perm_p = _sum_p_perm(task_eq, baseline_eq)

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
            "block_seconds":      windows_per_block * _WINDOW_DURATION_SEC,
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


@app.post("/analyze")
def analyze(body: Dict) -> Dict:
    """
    Analyse EEG task data vs baseline.

    Request:
      { "baseline": { "eyes_closed": [...], "eyes_open": [...] },
        "tasks":    { "<task_id>": [...], ... },
        "block_seconds": 8.0   # optional; default 8.0 s per block
      }

    Response mirrors EnhancedFeatureAnalysisEngine.multi_task_results structure.
    """
    baseline_raw: Dict[str, List] = body.get("baseline", {})
    tasks_raw:    Dict[str, List] = body.get("tasks",    {})

    # Optional block_seconds override (default _BLOCK_SECONDS = 8.0)
    req_block_sec    = body.get("block_seconds", _BLOCK_SECONDS)
    try:
        req_block_sec = max(0.5, float(req_block_sec))
    except (TypeError, ValueError):
        req_block_sec = _BLOCK_SECONDS
    win_per_block = max(1, round(req_block_sec / _WINDOW_DURATION_SEC))

    # Eyes-closed only for baseline (mirrors legacy: EC only, EO retained for reference)
    ec_samples: List = list(baseline_raw.get("eyes_closed", []) or [])
    eo_samples: List = list(baseline_raw.get("eyes_open",   []) or [])
    if not ec_samples:
        # Fall back to all baseline data if EC key absent
        for samples in baseline_raw.values():
            ec_samples.extend(samples if isinstance(samples, list) else [])

    if not ec_samples:
        return {"error": "No baseline data provided"}

    # Record raw counts before conversion (for report header)
    ec_raw_count = len(ec_samples)
    eo_raw_count = len(eo_samples)

    # Convert raw EEG directly to enhanced-style feature rows and apply
    # eyes-closed baseline QC before baseline statistics are finalized.
    baseline_rows, baseline_qc = _baseline_feature_rows(ec_samples)
    eo_rows = _samples_to_feature_rows(eo_samples)

    if not baseline_rows:
        return {"error": "No usable baseline data after quality control"}

    per_task:      Dict[str, Any] = {}
    per_task_rows: Dict[str, List[Dict]] = {}
    all_task_rows: List[Dict]     = []

    for task_id, samples in tasks_raw.items():
        if not samples:
            continue
        samples = list(samples)
        task_rows = _samples_to_feature_rows(samples)
        per_task_rows[task_id] = task_rows
        summary, analysis = _analyze_task_vs_baseline(
            task_rows, baseline_rows, task_id, win_per_block
        )
        per_task[task_id] = {
            "summary":      summary,
            "analysis":     analysis,
            "sample_count": len(task_rows),
        }
        all_task_rows.extend(task_rows)

    # ── Combined (all tasks pooled vs baseline) ───────────────────────────────
    comb_summary, comb_analysis = ({}, {})
    if all_task_rows:
        comb_summary, comb_analysis = _analyze_task_vs_baseline(
            all_task_rows, baseline_rows, windows_per_block=win_per_block
        )

    # ── Across-task omnibus (Kruskal-Wallis per feature + BH FDR) ─────────────
    n_sessions = len(per_task)
    fnames     = list(baseline_rows[0].keys()) if baseline_rows else []

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
        "baseline_rejected":          baseline_qc["rejected"],
        "baseline_rejected_not_worn": baseline_qc["not_worn"],
        "baseline_rejected_artifact": baseline_qc["artifact"],
        "baseline_rejected_flatline": baseline_qc["flatline"],
        "eo_windows":                 len(eo_rows),
        "config": {
            "mode":                "aggregate_only",
            "alpha":               _ALPHA,
            "fdr_alpha":           _FDR_ALPHA,
            "dependence_correction": "none",
            "runtime_preset":      "default",
            "n_perm":              _N_PERM,
            "effect_measure":      "delta",
            "discretization_bins": 5,
        },
    }

    # ── Neuroprofile traceability export (additive, does not alter existing keys) ─
    try:
        response["neuroprofile_feature_export"] = build_neuroprofile_export(
            per_task, response
        )
    except Exception as _npe:
        response["neuroprofile_feature_export"] = {
            "error": f"Neuroprofile export failed: {_npe}"
        }

    return response



# ─── WebSocket endpoint ───────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    _ws_clients.add(ws)
    # Immediately tell the new client the current connection state
    await ws.send_text(json.dumps({"type": "status", "value": _status}))
    try:
        while True:
            # Keep the WebSocket alive; we only push from the server side.
            # A 30-second ping prevents idle disconnection by proxies.
            await asyncio.sleep(30)
    except WebSocketDisconnect:
        pass
    finally:
        _ws_clients.discard(ws)


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)
