from types import SimpleNamespace
import unittest

from utils.enhanced_report_generator import Enhanced64ChannelReportGenerator


def _minimal_results(summary=None):
    return {
        "session_info": {
            "baseline_ec_windows": 8,
            "baseline_eo_windows": 8,
            "tasks_executed": 1,
            "n_channels": 64,
            "sample_rate": 500,
        },
        "artifact_summary": {},
        "multi_task_results": {
            "per_task": {
                "attention_focus": {
                    "summary": summary or {},
                    "analysis": {"per_feature": {}},
                }
            }
        },
    }


def _feature(p=0.01, q=0.02, d=1.0, sig=True, **extra):
    data = {
        "p_value": p,
        "q_value": q,
        "hedges_g": d,
        "task_mean": 2.0,
        "baseline_mean": 1.0,
        "significant": sig,
    }
    data.update(extra)
    return data


def _results_with_artifact_summary(artifact_summary):
    results = _minimal_results()
    results["artifact_summary"] = artifact_summary
    return results


class OfflineReportValidityTests(unittest.TestCase):
    def test_profile_suitability_counts_engine_gamma_flood_fields(self):
        summary = {
            "gamma_flood": {
                "detected": True,
                "total_gamma": 100,
                "sig_gamma": 40,
                "sig_fraction": 0.40,
                "threshold": 0.25,
            }
        }

        suitability, reasons, warnings = Enhanced64ChannelReportGenerator._compute_profile_suitability(
            _minimal_results(summary), excluded_tasks=set()
        )

        self.assertEqual(suitability, "RESEARCH-ONLY")
        self.assertTrue(any("Gamma EMG flood" in reason and "40%" in reason for reason in reasons))
        self.assertEqual(warnings, [])

    def test_fast_report_uses_actual_bootstrap_iterations(self):
        config = SimpleNamespace(
            apply_notch_filter=True,
            line_noise_freq=50.0,
            emg_adaptive_threshold=True,
            bootstrap_ci_samples=1000,
            n_boot=100,
            compute_bootstrap_ci=True,
            block_seconds=4.0,
            min_blocks_per_condition=8,
            apply_average_reference=True,
        )

        report = "\n".join(
            Enhanced64ChannelReportGenerator.generate_text_report(
                results=_minimal_results(),
                fast_mode=True,
                n_permutations=200,
                config=config,
            )
        )

        self.assertIn("Bootstrap 95% CI: 100 iterations", report)
        self.assertNotIn("Bootstrap 95% CI: 1000 iterations", report)

    def test_fast_report_does_not_claim_kost_mcdermott_correction(self):
        report = "\n".join(
            Enhanced64ChannelReportGenerator.generate_text_report(
                results=_minimal_results(),
                fast_mode=True,
                n_permutations=200,
                config=SimpleNamespace(),
            )
        )

        self.assertIn("dependence=independence approximation", report)
        self.assertNotIn("dependence=Kost-McDermott", report)
        self.assertNotIn("Fisher_KM: Fisher combined p-value adjusted", report)

    def test_report_includes_hf_epoch_rejection_summary_and_advanced_hook_status(self):
        artifact_summary = {
            "hf_artifact_rejection": {
                "enabled": True,
                "method": "adaptive_hf_ratio",
                "windows_tested": 20,
                "windows_rejected": 5,
                "forced_retained_windows": 1,
            },
            "advanced_emg_cleaning": {
                "ica_requested": True,
                "ica_applied": False,
                "ica_available": False,
                "csd_requested": True,
                "csd_applied": False,
                "csd_available": False,
                "cca_requested": True,
                "cca_applied": False,
                "cca_available": False,
            },
        }

        report = "\n".join(
            Enhanced64ChannelReportGenerator.generate_text_report(
                results=_results_with_artifact_summary(artifact_summary),
                fast_mode=True,
                n_permutations=200,
                config=SimpleNamespace(),
            )
        )

        self.assertIn("High-frequency epoch rejection: 5/20 windows rejected", report)
        self.assertIn("forced retained=1", report)
        self.assertIn("ICA EMG cleaning: requested, not applied", report)
        self.assertIn("CSD transform: requested, not applied", report)
        self.assertIn("CCA EMG cleaning: requested, not applied", report)

    def test_gamma_flood_suppresses_gamma_from_profile_facing_top_lists(self):
        summary = {
            "gamma_flood": {
                "detected": True,
                "total_gamma": 10,
                "sig_gamma": 6,
                "sig_fraction": 0.60,
                "threshold": 0.25,
            },
            "fisher": {},
            "sum_p": {},
            "composite": {},
        }
        results = _minimal_results(summary)
        per_feature = results["multi_task_results"]["per_task"]["attention_focus"]["analysis"]["per_feature"]
        per_feature["Fp2_gamma_power"] = _feature(p=0.0001, q=0.001, d=7.0, emg_excluded=True)
        per_feature["F3_alpha_power"] = _feature(p=0.001, q=0.01, d=1.5)

        report = "\n".join(
            Enhanced64ChannelReportGenerator.generate_text_report(
                results=results,
                fast_mode=True,
                n_permutations=200,
                config=SimpleNamespace(),
            )
        )

        top_list_start = report.index("Top 5 Features (by p-value, artifact-suspect/EMG-excluded excluded):")
        gamma_warning_start = report.index("--- GAMMA BAND RELIABILITY WARNING ---")
        self.assertNotIn("Fp2_gamma_power", report[top_list_start:gamma_warning_start])
        self.assertIn("EMG-excluded gamma diagnostics", report)
        self.assertIn("Fp2_gamma_power", report[gamma_warning_start:])

    def test_profile_gate_reports_hf_saturation_and_artifact_instances(self):
        results = _minimal_results({"gamma_flood": {}})
        per_task = results["multi_task_results"]["per_task"]
        per_task["mental_math"] = {"summary": {}, "analysis": {"per_feature": {}}}
        per_task["attention_focus"]["analysis"]["per_feature"] = {
            f"feat_{i}": _feature(d=11.0, artifact_suspect=True)
            for i in range(15)
        }
        per_task["mental_math"]["analysis"]["per_feature"] = {
            f"feat_{i}": _feature(d=12.0, artifact_suspect=True)
            for i in range(10)
        }
        results["artifact_summary"] = {
            "hf_artifact_rejection": {
                "enabled": True,
                "saturated_phases": 2,
                "candidate_rejected": 25,
            }
        }

        suitability, reasons, _ = Enhanced64ChannelReportGenerator._compute_profile_suitability(
            results, excluded_tasks=set()
        )

        self.assertEqual(suitability, "RESEARCH-ONLY")
        self.assertTrue(any("15 unique feature names / 25 task-feature instances" in r for r in reasons))
        self.assertTrue(any("High-frequency saturation guard activated in 2 phase" in r for r in reasons))

    def test_cross_task_fwer_no_significant_message(self):
        results = _minimal_results()
        results["multi_task_results"]["per_task"]["mental_math"] = {
            "summary": {},
            "analysis": {"per_feature": {}},
        }
        results["multi_task_results"]["cross_task_correction"] = {
            "method": "Holm-Bonferroni",
            "n_tasks": 2,
            "alpha": 0.05,
            "raw_pvals": {"attention_focus": 1.0, "mental_math": 1.0},
            "adjusted_pvals": {"attention_focus": 1.0, "mental_math": 1.0},
            "significant_tasks": [],
        }

        report = "\n".join(
            Enhanced64ChannelReportGenerator.generate_text_report(
                results=results,
                fast_mode=True,
                n_permutations=200,
                config=SimpleNamespace(),
            )
        )

        self.assertIn("No task-level omnibus effects survived Holm-Bonferroni", report)
        self.assertIn("No reliable between-task differentiation was detected.", report)
        self.assertNotIn("* Significant after family-wise error correction", report)

    def test_omnibus_q_less_than_p_suppresses_top_feature_stats(self):
        report_lines = Enhanced64ChannelReportGenerator._generate_omnibus_summary({
            "features": {
                "F8_beta_peak_freq": {
                    "omnibus_sig": True,
                    "statistic": 0.0,
                    "omnibus_p": 0.2,
                    "omnibus_q": 0.001,
                }
            },
            "fdr_alpha": 0.05,
        })
        report = "\n".join(report_lines)

        self.assertIn("Top Feature Omnibus Stats suppressed", report)
        self.assertNotIn("F8_beta_peak_freq: stat=", report)

    def test_spatial_sections_exclude_artifact_and_emg_features(self):
        lines = Enhanced64ChannelReportGenerator._generate_multichannel_summary(
            results={"artifact_summary": {}},
            analysis_results={
                "coh_temporal_parietal_alpha": _feature(d=-40.0, artifact_suspect=True),
                "coh_frontal_parietal_alpha": _feature(d=1.0),
                "Fp2_gamma_power": _feature(d=8.0, emg_excluded=True),
            },
            suitability="RESEARCH-ONLY",
        )
        report = "\n".join(lines)

        self.assertNotIn("coh_temporal_parietal_alpha", report)
        self.assertNotIn("Fp2_gamma_power", report)
        self.assertIn("coh_frontal_parietal_alpha", report)
        self.assertIn("Interpretation disabled: session is RESEARCH-ONLY", report)


if __name__ == "__main__":
    unittest.main()
