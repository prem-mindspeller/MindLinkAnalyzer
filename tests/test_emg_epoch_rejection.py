import unittest

import numpy as np

from antNeuro.offline_multichannel_analysis import OfflineMultichannelEngine


class EmgEpochRejectionTests(unittest.TestCase):
    def test_high_frequency_frontal_temporal_burst_window_is_rejected(self):
        fs = 500
        engine = OfflineMultichannelEngine(sample_rate=fs, channel_count=64)
        duration = 6.0
        n_samples = int(duration * fs)
        t = np.arange(n_samples) / fs

        data = np.zeros((n_samples, 64), dtype=float)
        for ch in range(64):
            data[:, ch] = 15.0 * np.sin(2 * np.pi * 10.0 * t)

        burst = (t >= 2.0) & (t < 4.0)
        affected = [
            idx for idx, name in enumerate(engine.channel_names)
            if name in {"Fp1", "Fp2", "F7", "F8", "F9", "F10", "FT7", "FT8", "T7", "T8"}
        ]
        for ch in affected:
            data[burst, ch] += 80.0 * np.sin(2 * np.pi * 40.0 * t[burst])

        window_samples = int(engine.window_size * fs)
        step_samples = int(window_samples * (1.0 - engine.window_overlap))
        rejected, metrics = engine._compute_high_frequency_artifact_mask(
            data, window_samples, step_samples
        )

        self.assertGreaterEqual(int(np.sum(rejected)), 1)
        self.assertGreater(metrics["max_frontotemporal_ratio"], metrics["frontotemporal_ratio_threshold"])
        self.assertEqual(metrics["method"], "adaptive_hf_ratio")

    def test_clean_alpha_windows_are_not_rejected(self):
        fs = 500
        engine = OfflineMultichannelEngine(sample_rate=fs, channel_count=64)
        duration = 6.0
        n_samples = int(duration * fs)
        t = np.arange(n_samples) / fs

        data = np.zeros((n_samples, 64), dtype=float)
        rng = np.random.default_rng(7)
        for ch in range(64):
            data[:, ch] = (
                15.0 * np.sin(2 * np.pi * 10.0 * t)
                + rng.normal(0.0, 1.0, size=n_samples)
            )

        window_samples = int(engine.window_size * fs)
        step_samples = int(window_samples * (1.0 - engine.window_overlap))
        rejected, metrics = engine._compute_high_frequency_artifact_mask(
            data, window_samples, step_samples
        )

        self.assertEqual(int(np.sum(rejected)), 0)
        self.assertEqual(metrics["n_windows"], len(rejected))

    def test_tonic_high_frequency_contamination_is_not_forced_into_tiny_sample(self):
        fs = 500
        engine = OfflineMultichannelEngine(sample_rate=fs, channel_count=64)
        duration = 10.0
        n_samples = int(duration * fs)
        t = np.arange(n_samples) / fs

        data = np.zeros((n_samples, 64), dtype=float)
        for ch in range(64):
            data[:, ch] = (
                15.0 * np.sin(2 * np.pi * 10.0 * t)
                + 40.0 * np.sin(2 * np.pi * 40.0 * t)
            )

        window_samples = int(engine.window_size * fs)
        step_samples = int(window_samples * (1.0 - engine.window_overlap))
        rejected, metrics = engine._compute_high_frequency_artifact_mask(
            data, window_samples, step_samples
        )

        self.assertEqual(int(np.sum(rejected)), 0)
        self.assertTrue(metrics["saturated"])
        self.assertIn("exceeds max rejection fraction", metrics["reason"])


if __name__ == "__main__":
    unittest.main()
