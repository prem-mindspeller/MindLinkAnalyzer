import argparse
import asyncio
import json
import time
from collections.abc import AsyncGenerator

import websockets

from .config import FocusCubeConfig
from .features import demo_frame, warming_frame
from .mindrove_source import MindRoveRawSource


def log(message: str) -> None:
    print(f"[FocusCube] {message}", flush=True)


async def create_frame_stream(
    config: FocusCubeConfig,
    demo: bool = False,
    require_device: bool = False,
    command_queue: asyncio.Queue | None = None,
) -> AsyncGenerator[dict, None]:
    source: MindRoveRawSource | None = None
    start = time.monotonic()

    if not demo:
        source = MindRoveRawSource(config)
        try:
            log(
                "Starting MindRove Bright stream "
                f"ip={config.mindrove_ip_address} port={config.mindrove_ip_port}..."
            )
            source.start()
            log(
                f"MindRove source started device={source.device_name} "
                f"sample_rate={source.sample_rate} eeg_channels={source.eeg_channels}; "
                "waiting for raw samples."
            )
        except Exception as exc:
            if require_device:
                raise
            source = None
            demo = True
            log(f"{exc}. Falling back to demo stream. Use --require-device to fail instead.")
    else:
        log("Demo stream forced with --demo.")

    try:
        last_log = 0.0
        while True:
            if source and command_queue:
                while not command_queue.empty():
                    command = await command_queue.get()
                    if command == "reset_calibration":
                        source.reset_calibration()
                        log("Calibration reset from browser.")
            payload = None
            if source:
                payload = source.payload()
            if payload is None:
                if source:
                    payload = warming_frame(config, source.sample_count, source.device_status)
                else:
                    payload = demo_frame(time.monotonic() - start, config)
            now = time.monotonic()
            if now - last_log >= 1.0:
                log_payload_summary(payload)
                last_log = now
            yield payload
            await asyncio.sleep(0.08)
    finally:
        if source:
            source.stop()


def log_payload_summary(payload: dict) -> None:
    mode = payload.get("mode", "unknown")
    device = payload.get("device", {})
    battery = device.get("battery")
    battery_text = f"{battery}%" if battery is not None else "n/a"
    endpoint = _device_endpoint(device)
    sample_count = device.get("sampleCount", payload.get("sampleCount", 0))
    if mode == "device":
        bands = payload["bands"]
        normalized = payload["normalized"]
        focus = payload.get("focus", {})
        components = focus.get("components", {})
        log(
            "features "
            f"mode=device endpoint={endpoint} battery={battery_text} samples={sample_count} "
            f"attention={payload['attention']:.2f} quality={payload['quality']:.2f} "
            f"alpha={bands['alpha']:.3f} beta={bands['beta']:.3f} gamma={bands['gamma']:.3f} "
            f"focus={normalized.get('focusIndex', 0):.2f} "
            f"frontal_engagement={components.get('frontalEngagement', 0):.2f} "
            f"occipital_alpha_suppression={components.get('occipitalAlphaSuppression', 0):.2f} "
            f"artifact_penalty={components.get('artifactPenalty', 0):.2f}"
        )
    elif mode == "device_calibrating":
        focus = payload.get("focus", {})
        progress = focus.get("baselineProgress", device.get("baselineProgress", 0.0))
        count = focus.get("baselineCount", device.get("baselineCount", 0))
        required = focus.get("baselineRequired", device.get("baselineRequired", "?"))
        log(
            f"calibrating mode=device_calibrating endpoint={endpoint} battery={battery_text} "
            f"samples={sample_count} baseline={progress:.0%} windows={count}/{required}"
        )
    elif mode == "device_warming":
        log(
            f"warming mode=device_warming endpoint={endpoint} battery={battery_text} "
            f"samples={sample_count}/{payload.get('requiredSamples')}"
        )
    elif mode == "device_not_worn":
        contact = device.get("contactQuality", 0.0)
        resistances = device.get("resistanceOhms") or []
        eeg_stds = device.get("eegRowStd") or []
        resistance_text = ",".join(f"{value:.0f}" for value in resistances[:6]) or "n/a"
        eeg_std_text = ",".join(f"{value:.1f}" for value in eeg_stds[:4]) or "n/a"
        log(
            f"not_worn mode=device_not_worn endpoint={endpoint} battery={battery_text} "
            f"contact={contact:.2f} reason={device.get('contactReason', 'unknown')} "
            f"resistance_ohms=[{resistance_text}] eeg_std=[{eeg_std_text}] samples={sample_count}"
        )
    elif mode == "demo":
        log("features mode=demo synthetic=true no real MindRove device data")


def _device_endpoint(device: dict) -> str:
    if device.get("serialPort"):
        return str(device["serialPort"])
    if device.get("ipAddress"):
        return f"{device['ipAddress']}:{device.get('ipPort', 'n/a')}"
    return "n/a"


async def run_server(config: FocusCubeConfig, demo: bool, require_device: bool) -> None:
    clients: set[websockets.ServerConnection] = set()
    command_queue: asyncio.Queue = asyncio.Queue()

    async def handler(websocket):
        clients.add(websocket)
        try:
            async for message in websocket:
                try:
                    payload = json.loads(message)
                except json.JSONDecodeError:
                    continue
                if payload.get("type") == "reset_calibration":
                    await command_queue.put("reset_calibration")
        finally:
            clients.discard(websocket)

    async with websockets.serve(handler, config.websocket_host, config.websocket_port):
        log(f"WebSocket server listening on ws://{config.websocket_host}:{config.websocket_port}")
        async for payload in create_frame_stream(
            config,
            demo=demo,
            require_device=require_device,
            command_queue=command_queue,
        ):
            if not clients:
                continue
            message = json.dumps(payload)
            await asyncio.gather(
                *(client.send(message) for client in list(clients)),
                return_exceptions=True,
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MindLink Focus Cube WebSocket backend")
    parser.add_argument("--demo", action="store_true", help="Force synthetic demo data")
    parser.add_argument("--require-device", action="store_true", help="Fail instead of falling back to demo mode")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--mindrove-ip", default="192.168.4.1", help="MindRove WiFi shield IP address")
    parser.add_argument("--mindrove-port", type=int, default=4210, help="MindRove WiFi UDP/TCP port")
    parser.add_argument("--mindrove-serial-port", help="Optional MindRove serial port if your SDK setup needs one")
    parser.add_argument("--mindrove-timeout", type=int, default=10, help="MindRove SDK connection timeout in seconds")
    parser.add_argument("--eeg-rows", default="0,1,4,5", help="Comma-separated MindRove Bright EEG rows, default Fp1,Fp2,O1,O2")
    parser.add_argument("--worn-resistance-threshold", type=float, default=5_000_000.0, help="Max impedance/resistance considered good contact")
    parser.add_argument("--worn-min-good-resistance-pairs", type=int, default=2, help="Minimum good resistance pairs before headset is treated as worn")
    parser.add_argument("--contact-mode", choices=("auto", "resistance", "eeg"), default="auto", help="How to detect worn/contact state")
    parser.add_argument("--worn-min-active-eeg-rows", type=int, default=2, help="Minimum plausible active EEG rows in auto/eeg contact mode")
    parser.add_argument("--worn-min-eeg-std", type=float, default=0.5, help="Minimum per-row EEG standard deviation for contact fallback")
    parser.add_argument("--worn-max-eeg-std", type=float, default=50000.0, help="Maximum per-row EEG standard deviation for contact fallback")
    parser.add_argument("--focus-deadband", type=float, default=0.03, help="Fractional change ignored around baseline before focus scoring")
    parser.add_argument("--focus-full-scale", type=float, default=0.25, help="Fractional change that maps a component to full focus score")
    parser.add_argument("--disable-worn-gate", action="store_true", help="Disable contact gating and let raw EEG drive the cube")
    parser.add_argument("--print-raw", action="store_true", help="Print throttled channel-wise raw MindRove EEG rows")
    parser.add_argument("--raw-print-rows", type=int, default=8, help="Number of EEG rows to include in raw debug output")
    parser.add_argument("--raw-print-samples", type=int, default=8, help="Number of recent samples per EEG row to print")
    parser.add_argument("--raw-print-interval", type=float, default=1.0, help="Seconds between raw debug output lines")
    parser.add_argument(
        "--attention-source",
        choices=("focus_index", "alpha", "inverse_alpha", "beta_alpha_ratio"),
        default="focus_index",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    log("Starting MindLink Focus Cube backend.")
    log(f"Attention source: {args.attention_source}")
    config = FocusCubeConfig(
        websocket_host=args.host,
        websocket_port=args.port,
        attention_source=args.attention_source,
        mindrove_ip_address=args.mindrove_ip,
        mindrove_ip_port=args.mindrove_port,
        mindrove_serial_port=args.mindrove_serial_port,
        mindrove_timeout=args.mindrove_timeout,
        mindrove_eeg_rows=parse_eeg_rows(args.eeg_rows),
        worn_resistance_threshold=args.worn_resistance_threshold,
        worn_min_good_resistance_pairs=args.worn_min_good_resistance_pairs,
        contact_mode=args.contact_mode,
        worn_min_active_eeg_rows=args.worn_min_active_eeg_rows,
        worn_min_eeg_std=args.worn_min_eeg_std,
        worn_max_eeg_std=args.worn_max_eeg_std,
        focus_deadband=args.focus_deadband,
        focus_percent_change_full_scale=args.focus_full_scale,
        disable_worn_gate=args.disable_worn_gate,
        print_raw=args.print_raw,
        raw_print_rows=args.raw_print_rows,
        raw_print_samples=args.raw_print_samples,
        raw_print_interval=args.raw_print_interval,
    )
    asyncio.run(run_server(config, demo=args.demo, require_device=args.require_device))


def parse_eeg_rows(value: str) -> tuple[int, ...]:
    rows = tuple(int(part.strip()) for part in value.split(",") if part.strip())
    if not rows:
        raise argparse.ArgumentTypeError("At least one EEG row is required")
    return rows


if __name__ == "__main__":
    main()
