from dataclasses import dataclass


@dataclass(frozen=True)
class FocusCubeConfig:
    sample_rate: int = 256
    window_size: int = 256
    overlap_size: int = 128
    normalizer_window: int = 120
    attention_source: str = "alpha"
    lift_smoothing: float = 0.12
    lift_threshold: float = 0.6
    websocket_host: str = "127.0.0.1"
    websocket_port: int = 8765
    serial_baud: int = 115200
    allow_pure_parser: bool = False
    serial_port: str | None = None
