#!/usr/bin/env python3
"""
Build calibrated Task 11 (Speech-in-Noise Comprehension) audio assets.

Takes narration recordings for the three parallel forms (speech_a, speech_b,
speech_c) and mixes each with the same seeded noise the uncalibrated runtime
path already generates, at a measured target SNR. Writes one WAV per form,
computes its sha256, and prints the config block to paste into
optimizedBatteryProfile.mjs's `speech_in_noise` audio profile.

This tool cannot produce the narration itself — record it, or generate it with
whatever TTS you have available, as plain speech with no noise. Steady studio
or room-tone noise under the narration is fine (it will be summed with the
calibrated noise); anything already containing bursty or speech-like noise
will corrupt the SNR measurement.

Usage:
    # Point at a directory containing speech_a.wav, speech_b.wav, speech_c.wav
    python3 build_speech_in_noise_assets.py --narration-dir ./narration

    # Or name each file explicitly (any subset of the three forms)
    python3 build_speech_in_noise_assets.py \\
        --narration speech_a=narration/a.wav \\
        --narration speech_b=narration/b.wav \\
        --narration speech_c=narration/c.wav

    # Prove the pipeline works without real narration
    python3 build_speech_in_noise_assets.py --selftest

Run the project's tests first if you have not: see
speech_in_noise_mixer.test.py in this directory.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

from speech_in_noise_mixer import (
    AudioValidationError,
    MixResult,
    mix_speech_in_noise,
    read_narration_wav,
    write_pcm16_wav,
)

FORM_IDS = ("speech_a", "speech_b", "speech_c")
DEFAULT_SEED = 11011
DEFAULT_BUFFER_SECONDS = 2.0
DEFAULT_TARGET_SNR_DB = 8.0
# Matches optimizedBatteryProfile.mjs's speech-in-noise passage length.
SELFTEST_DURATION_SECONDS = 6.0
SELFTEST_SAMPLE_RATE = 44100


def _snr_suffix(target_snr_db: float) -> str:
    text = f"{target_snr_db:g}".replace("-", "neg").replace(".", "p")
    return f"snr{text}"


def _parse_narration_args(pairs: list[str]) -> dict[str, Path]:
    narration = {}
    for pair in pairs:
        if "=" not in pair:
            raise SystemExit(f"--narration expects form_id=path, got: {pair!r}")
        form_id, path = pair.split("=", 1)
        form_id = form_id.strip()
        if form_id not in FORM_IDS:
            raise SystemExit(f"Unknown form id {form_id!r}; expected one of {FORM_IDS}")
        narration[form_id] = Path(path).expanduser()
    return narration


def _resolve_narration_sources(args: argparse.Namespace) -> dict[str, Path]:
    if args.narration_dir:
        directory = Path(args.narration_dir).expanduser()
        found = {
            form_id: directory / f"{form_id}.wav"
            for form_id in FORM_IDS
            if (directory / f"{form_id}.wav").exists()
        }
        if not found:
            raise SystemExit(
                f"No speech_a.wav / speech_b.wav / speech_c.wav found under {directory}"
            )
        return found
    return _parse_narration_args(args.narration)


def _write_selftest_narration(directory: Path) -> dict[str, Path]:
    """Synthetic stand-in narration: three distinct tone/envelope patterns.

    Not real speech — this only proves the mixing pipeline (noise generation,
    SNR calibration, normalisation, WAV I/O, hashing) runs correctly end to
    end. Do not ship these files.
    """
    directory.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed=1)
    n = int(SELFTEST_SAMPLE_RATE * SELFTEST_DURATION_SECONDS)
    t = np.arange(n) / SELFTEST_SAMPLE_RATE
    sources: dict[str, Path] = {}
    for index, form_id in enumerate(FORM_IDS):
        # A steady tone with slow amplitude modulation stands in for a voice's
        # energy envelope, at a distinct pitch per form.
        tone = np.sin(2 * np.pi * (220 + index * 80) * t)
        envelope = 0.6 + 0.4 * np.sin(2 * np.pi * 0.5 * t)
        placeholder = 0.5 * tone * envelope + 0.01 * rng.standard_normal(n)
        path = directory / f"{form_id}.wav"
        write_pcm16_wav(path, placeholder, SELFTEST_SAMPLE_RATE)
        sources[form_id] = path
    return sources


def _print_config_block(results: list[MixResult], target_snr_db: float) -> None:
    lines = ["", "Paste into speech_in_noise in optimizedBatteryProfile.mjs:", ""]
    lines.append("  mode: 'premixed_audio_asset',")
    lines.append("  assetsByForm: {")
    for result in results:
        rel = f"audio/{result.output_path.name}"
        lines.append(f"    {result.form_id}: {{ uri: '{rel}', sha256: '{result.sha256}' }},")
    lines.append("  },")
    lines.append(f"  nominalSnrDb: {target_snr_db:g},")
    lines.append("  acousticallyCalibrated: true,")
    print("\n".join(lines))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--narration-dir", help="directory containing speech_a.wav / speech_b.wav / speech_c.wav")
    parser.add_argument("--narration", action="append", default=[], help="form_id=path, repeatable")
    parser.add_argument("--target-snr-db", type=float, default=DEFAULT_TARGET_SNR_DB)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="must match the runtime noise seed to stay consistent with the uncalibrated design")
    parser.add_argument("--buffer-seconds", type=float, default=DEFAULT_BUFFER_SECONDS)
    parser.add_argument(
        "--output-dir",
        default=str(Path(__file__).resolve().parent.parent / "src" / "assets" / "audio"),
        help="default: ElectronFrontEnd/src/assets/audio (copied to dist/audio by webpack)",
    )
    parser.add_argument("--selftest", action="store_true", help="use synthetic placeholder narration instead of real files")
    args = parser.parse_args(argv)

    if args.selftest:
        narration_sources = _write_selftest_narration(Path(args.output_dir) / "_selftest_narration")
        print("SELF-TEST MODE: using synthetic placeholder narration, not real speech.\n")
    else:
        narration_sources = _resolve_narration_sources(args)

    output_dir = Path(args.output_dir)
    results: list[MixResult] = []
    for form_id, narration_path in narration_sources.items():
        try:
            narration, sample_rate = read_narration_wav(narration_path)
            output_path = output_dir / f"{form_id}_{_snr_suffix(args.target_snr_db)}.wav"
            result = mix_speech_in_noise(
                form_id=form_id,
                narration=narration,
                sample_rate=sample_rate,
                output_path=output_path,
                target_snr_db=args.target_snr_db,
                seed=args.seed,
                buffer_seconds=args.buffer_seconds,
            )
        except AudioValidationError as error:
            print(f"SKIPPED {form_id}: {error}", file=sys.stderr)
            continue
        results.append(result)
        deviation = abs(result.achieved_snr_db - args.target_snr_db)
        flag = "" if deviation < 0.05 else "  ** achieved SNR deviates from target, check narration levels **"
        print(
            f"{result.form_id}: {result.duration_seconds:.1f}s @ {result.sample_rate} Hz | "
            f"target {result.target_snr_db:.2f} dB, achieved {result.achieved_snr_db:.2f} dB{flag}"
        )
        print(f"  -> {result.output_path}")
        print(f"  sha256: {result.sha256}")

    if not results:
        print("No assets were produced.", file=sys.stderr)
        return 1

    missing = set(FORM_IDS) - {r.form_id for r in results}
    if missing:
        print(f"\nNote: no narration supplied for {sorted(missing)}; config block below is partial.")

    _print_config_block(results, args.target_snr_db)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
