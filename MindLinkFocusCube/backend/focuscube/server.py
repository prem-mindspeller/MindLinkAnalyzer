import argparse
import asyncio
import json
import time
from collections.abc import AsyncGenerator

import websockets

from .brainlink_source import BrainLinkRawSource, describe_ports
from .config import FocusCubeConfig
from .features import demo_frame, warming_frame


def log(message: str) -> None:
    print(f"[FocusCube] {message}", flush=True)


async def create_frame_stream(
    config: FocusCubeConfig,
    demo: bool = False,
    require_device: bool = False,
    allow_pure_parser: bool = False,
) -> AsyncGenerator[dict, None]:
    source: BrainLinkRawSource | None = None
    start = time.monotonic()

    if not demo:
        source = BrainLinkRawSource(
            config,
            port=getattr(config, "serial_port", None),
            allow_pure_parser=allow_pure_parser,
        )
        try:
            log("Searching for BrainLink serial device...")
            source.start()
            log(f"BrainLink source started on {source.port}; waiting for raw samples.")
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
    port = device.get("port") or "n/a"
    sample_count = device.get("sampleCount", payload.get("sampleCount", 0))
    if mode == "device":
        bands = payload["bands"]
        normalized = payload["normalized"]
        log(
            "features "
            f"mode=device port={port} battery={battery_text} samples={sample_count} "
            f"attention={payload['attention']:.2f} quality={payload['quality']:.2f} "
            f"alpha={bands['alpha']:.3f} beta={bands['beta']:.3f} gamma={bands['gamma']:.3f} "
            f"norm_alpha={normalized['alpha']:.2f} norm_beta_gamma={normalized['betaGamma']:.2f}"
        )
    elif mode == "device_warming":
        log(
            f"warming mode=device_warming port={port} battery={battery_text} "
            f"samples={sample_count}/{payload.get('requiredSamples')}"
        )
    elif mode == "demo":
        log("features mode=demo synthetic=true no real BrainLink device data")


async def run_server(config: FocusCubeConfig, demo: bool, require_device: bool) -> None:
    clients: set[websockets.ServerConnection] = set()

    async def handler(websocket):
        clients.add(websocket)
        try:
            await websocket.wait_closed()
        finally:
            clients.discard(websocket)

    async with websockets.serve(handler, config.websocket_host, config.websocket_port):
        log(f"WebSocket server listening on ws://{config.websocket_host}:{config.websocket_port}")
        async for payload in create_frame_stream(
            config,
            demo=demo,
            require_device=require_device,
            allow_pure_parser=getattr(config, "allow_pure_parser", False),
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
    parser.add_argument(
        "--allow-pure-parser",
        action="store_true",
        help="Allow protocol-only pure Python TGAM fallback if native BrainLinkParser.pyd cannot load",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--serial-port", help="Explicit BrainLink serial port, e.g. COM8")
    parser.add_argument("--list-ports", action="store_true", help="Print serial ports and exit")
    parser.add_argument(
        "--attention-source",
        choices=("alpha", "inverse_alpha", "beta_alpha_ratio"),
        default="alpha",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.list_ports:
        for port in describe_ports():
            log(
                f"port={port['device']} desc={port['description']} "
                f"hwid={port['hwid']} manufacturer={port['manufacturer']} "
                f"serial={port['serialNumber']}"
            )
        return

    log("Starting MindLink Focus Cube backend.")
    log(f"Attention source: {args.attention_source}")
    config = FocusCubeConfig(
        websocket_host=args.host,
        websocket_port=args.port,
        attention_source=args.attention_source,
        allow_pure_parser=args.allow_pure_parser,
        serial_port=args.serial_port,
    )
    asyncio.run(run_server(config, demo=args.demo, require_device=args.require_device))


if __name__ == "__main__":
    main()
