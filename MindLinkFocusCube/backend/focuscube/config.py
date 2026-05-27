from dataclasses import dataclass


@dataclass(frozen=True)
class FocusCubeConfig:
    sample_rate: int = 500
    window_size: int = 1000
    overlap_size: int = 500
    focus_update_stride_samples: int = 500
    normalizer_window: int = 120
    attention_source: str = "focus_index"
    calibration_windows: int = 12
    focus_smoothing: float = 0.18
    focus_engagement_weight: float = 0.55
    focus_occipital_alpha_weight: float = 0.30
    focus_frontal_alpha_weight: float = 0.15
    focus_alpha_activation_weight: float = 0.75
    focus_percent_change_full_scale: float = 0.25
    focus_deadband: float = 0.03
    artifact_hf_ratio_threshold: float = 0.35
    artifact_line_ratio_threshold: float = 0.12
    lift_smoothing: float = 0.12
    lift_threshold: float = 0.6
    websocket_host: str = "127.0.0.1"
    websocket_port: int = 8765
    mindrove_ip_address: str = "192.168.4.1"
    mindrove_ip_port: int = 4210
    mindrove_serial_port: str | None = None
    mindrove_timeout: int = 10
    mindrove_eeg_rows: tuple[int, ...] | None = None
    worn_resistance_threshold: float = 5_000_000.0
    worn_min_good_resistance_pairs: int = 2
    contact_mode: str = "auto"
    worn_min_active_eeg_rows: int = 4
    worn_min_eeg_std: float = 0.5
    worn_max_eeg_std: float = 50_000.0
    worn_max_abs_mean: float = 0.0
    worn_required_consecutive_frames: int = 3
    disable_worn_gate: bool = False
    print_raw: bool = False
    raw_print_rows: int = 8
    raw_print_samples: int = 8
    raw_print_interval: float = 1.0
