import unittest

from antNeuro.offline_multichannel_analysis import OfflineMultichannelEngine


class MissingFeatureStatisticsTests(unittest.TestCase):
    def test_task_analysis_does_not_zero_fill_missing_channel_features(self):
        engine = OfflineMultichannelEngine(sample_rate=500, channel_count=64)
        engine.config.block_seconds = 1.0
        engine.window_size = 1.0
        engine.window_overlap = 0.0
        engine.config.n_boot = 10

        engine.calibration_data["eyes_closed"]["features"] = [
            {"FC2_delta_power": 1.0, "F3_delta_power": 1.0},
            {"FC2_delta_power": 1.1, "F3_delta_power": 1.1},
            {"FC2_delta_power": 0.9, "F3_delta_power": 0.9},
            {"FC2_delta_power": 1.2, "F3_delta_power": 1.2},
        ]
        engine.calibration_data["task"]["features"] = [
            {"F3_delta_power": 2.0},
            {"F3_delta_power": 2.1},
            {"F3_delta_power": 1.9},
            {"F3_delta_power": 2.2},
        ]

        engine.compute_baseline_statistics()
        analysis = engine.analyze_task_data()

        self.assertNotIn("FC2_delta_power", analysis["per_feature"])
        self.assertIn("F3_delta_power", analysis["per_feature"])


if __name__ == "__main__":
    unittest.main()
