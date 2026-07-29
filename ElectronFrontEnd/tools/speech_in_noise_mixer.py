"""
Core DSP for building calibrated Task 11 (Speech-in-Noise Comprehension) audio.

Mixes narration with the same seeded noise the uncalibrated runtime path
generates (optimizedBatteryProfile.mjs audioProfiles.speech_in_noise.noise:
seeded_white_noise, seed 11011, looped from a short buffer), scaled to hit a
target SNR that is then re-measured from the output, not assumed.

Kept import-free of anything outside numpy/stdlib so it can be unit tested
without the rest of the Electron toolchain.
"""
from __future__ import annotations

import hashlib
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# Must match the LCG in OptimizedBatteryTask.jsx's noise generator exactly:
#   seed = (1664525 * seed + 1013904223) >>> 0
#   sample = (seed / 4294967296) * 2 - 1
LCG_MULTIPLIER = 1664525
LCG_INCREMENT = 1013904223
LCG_MODULUS = 2 ** 32

# -1 dBFS peak headroom, applied uniformly to narration and noise together so
# the SNR ratio is unaffected and loudness is consistent across forms.
TARGET_PEAK = 10 ** (-1 / 20)

PCM16_MAX = 32767


class AudioValidationError(ValueError):
    """Narration input is unusable for calibrated mixing."""


@dataclass(frozen=True)
class MixResult:
    form_id: str
    output_path: Path
    sha256: str
    sample_rate: int
    duration_seconds: float
    target_snr_db: float
    achieved_snr_db: float
    narration_rms: float
    noise_rms: float


def generate_seeded_noise(seed: int, length: int) -> np.ndarray:
    """Reproduce the runtime's seeded LCG noise, unit-amplitude (unscaled)."""
    seed = int(seed) & 0xFFFFFFFF
    samples = np.empty(length, dtype=np.float64)
    for index in range(length):
        seed = (LCG_MULTIPLIER * seed + LCG_INCREMENT) % LCG_MODULUS
        samples[index] = (seed / LCG_MODULUS) * 2 - 1
    return samples


def looped_noise(seed: int, buffer_seconds: float, sample_rate: int, total_samples: int) -> np.ndarray:
    """The runtime loops one seeded buffer rather than generating fresh values
    for the whole duration (WebAudioBufferSourceNode.loop = true)."""
    buffer_length = max(1, int(sample_rate * buffer_seconds))
    base = generate_seeded_noise(seed, buffer_length)
    repeats = -(-total_samples // buffer_length)  # ceil
    return np.tile(base, repeats)[:total_samples]


def _rms(samples: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(samples)))) if samples.size else 0.0


def read_narration_wav(path: Path) -> tuple[np.ndarray, int]:
    """Read a WAV file as float64 samples in [-1, 1], downmixed to mono.

    Only 16-bit PCM is supported; anything else fails loudly rather than
    silently mis-decoding.
    """
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        sample_width = handle.getsampwidth()
        sample_rate = handle.getframerate()
        frame_count = handle.getnframes()
        raw = handle.readframes(frame_count)

    if sample_width != 2:
        raise AudioValidationError(
            f"{path}: expected 16-bit PCM WAV, found {sample_width * 8}-bit. "
            "Convert with `ffmpeg -i in.wav -acodec pcm_s16le out.wav` first."
        )
    if frame_count == 0:
        raise AudioValidationError(f"{path}: contains no audio frames.")

    samples = np.frombuffer(raw, dtype="<i2").astype(np.float64) / (PCM16_MAX + 1)
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return samples, sample_rate


def write_pcm16_wav(path: Path, samples: np.ndarray, sample_rate: int) -> None:
    clipped = np.clip(samples, -1.0, 1.0)
    ints = np.round(clipped * PCM16_MAX).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(ints.tobytes())


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def mix_speech_in_noise(
    form_id: str,
    narration: np.ndarray,
    sample_rate: int,
    output_path: Path,
    target_snr_db: float = 8.0,
    seed: int = 11011,
    buffer_seconds: float = 2.0,
    min_narration_rms: float = 1e-4,
) -> MixResult:
    """Mix narration with seeded noise at a measured target SNR and write it out.

    The achieved SNR is recomputed from the final, peak-normalised signal
    components rather than assumed equal to the target, so a bug in the scale
    calculation would show up as a reported mismatch instead of silently
    passing.
    """
    narration_rms = _rms(narration)
    if narration_rms < min_narration_rms:
        raise AudioValidationError(
            f"{form_id}: narration is near-silent (RMS={narration_rms:.6f}); "
            "cannot calibrate an SNR against it."
        )

    noise_base = looped_noise(seed, buffer_seconds, sample_rate, narration.size)
    noise_base_rms = _rms(noise_base)

    # 20*log10(rms_speech / rms_noise) = target_snr_db  =>  solve for rms_noise.
    desired_noise_rms = narration_rms / (10 ** (target_snr_db / 20))
    noise_scale = desired_noise_rms / noise_base_rms
    noise_scaled = noise_base * noise_scale

    mixed = narration + noise_scaled
    peak = float(np.max(np.abs(mixed))) if mixed.size else 0.0
    final_scale = (TARGET_PEAK / peak) if peak > 0 else 1.0

    narration_final = narration * final_scale
    noise_final = noise_scaled * final_scale
    mixed_final = narration_final + noise_final

    achieved_snr_db = 20 * np.log10(_rms(narration_final) / _rms(noise_final))

    write_pcm16_wav(output_path, mixed_final, sample_rate)

    return MixResult(
        form_id=form_id,
        output_path=output_path,
        sha256=sha256_of(output_path),
        sample_rate=sample_rate,
        duration_seconds=narration.size / sample_rate,
        target_snr_db=target_snr_db,
        achieved_snr_db=float(achieved_snr_db),
        narration_rms=narration_rms,
        noise_rms=_rms(noise_final),
    )
