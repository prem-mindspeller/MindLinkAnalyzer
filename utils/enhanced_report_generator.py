#!/usr/bin/env python3
"""
Enhanced Report Generator for 64-Channel Multi-Task EEG Analysis

Generates comprehensive reports matching the single-channel format with  
64-channel specific enhancements.

Author: BrainLink Companion Team
Date: February 2026
"""

import numpy as np
from typing import Dict, List, Any, Optional
from datetime import datetime


class Enhanced64ChannelReportGenerator:
    """Generates comprehensive reports for 64-channel EEG analysis."""
    
    @staticmethod
    def generate_text_report(results: Dict[str, Any], fast_mode: bool, n_permutations: int,
                             config: Any = None, force_analysis: bool = False) -> List[str]:
        """
        Generate enhanced text report matching single-channel format exactly.
        
        Parameters
        ----------
        results : dict
            Analysis results dictionary
        fast_mode : bool
            Whether analysis used fast/parametric mode
        n_permutations : int
            Number of permutations used (for block-level SumP test)
        config : EnhancedAnalyzerConfig, optional
            Configuration object with preprocessing settings
        force_analysis : bool, optional
            When True, retain all quality warnings but do not suppress results
            even when data quality is poor (e.g. known high-impedance recordings).
        
        Returns
        -------
        List[str]
            Lines of formatted report text
        """
        lines = []
        
        # Tasks to exclude from report (data collection only, analyzed offline separately)
        excluded_tasks = {'40hz_stimulation', 'gamma_entrainment'}
        
        # ===== HEADER =====
        lines.append("MindLink Enhanced 64-Channel Multi-Task Analysis Report")
        lines.append("="*72)
        lines.append(f"UTC Timestamp: {datetime.utcnow().isoformat()}+00:00")
        
        # Get session info
        session_info = results.get('session_info', {})
        
        # Extract and display subject metadata if available
        subject_metadata = session_info.get('subject_metadata', {})
        if subject_metadata:
            lines.append("")
            lines.append("Subject Information")
            lines.append("-"*72)
            subject_id = subject_metadata.get('id', 'UNKNOWN')
            subject_age = subject_metadata.get('age', 'N/A')
            subject_email = subject_metadata.get('email', 'N/A')
            lines.append(f"Subject ID: {subject_id}")
            lines.append(f"Age: {subject_age} years" if subject_age != 'N/A' else "Age: N/A")
            lines.append(f"Email: {subject_email}")
            lines.append("")
        
        # Count baseline and task windows from session_info or multi_task_results
        baseline_ec = session_info.get('baseline_ec_windows', 0)
        baseline_eo = session_info.get('baseline_eo_windows', 0)
        tasks_executed = session_info.get('tasks_executed', 0)
        
        # If not in session_info, try to count from multi_task_results
        multi_task = results.get('multi_task_results', {})
        per_task = multi_task.get('per_task', {})
        if tasks_executed == 0:
            tasks_executed = len(per_task)
        analyzed_task_names = sorted(
            task_name for task_name in per_task.keys()
            if task_name.lower() not in excluded_tasks
        )
        explicitly_excluded_tasks = sorted(
            task_name for task_name in per_task.keys()
            if task_name.lower() in excluded_tasks
        )
        inferred_excluded_count = max(0, int(tasks_executed or 0) - len(analyzed_task_names))
        
        lines.append(f"Baseline EC windows: {baseline_ec} | EO windows: {baseline_eo}")
        lines.append(f"Tasks executed: {tasks_executed}")
        if per_task:
            lines.append(f"Tasks analyzed statistically: {len(analyzed_task_names)}")
            if explicitly_excluded_tasks or inferred_excluded_count > 0:
                lines.append("Excluded from statistical comparison:")
                if explicitly_excluded_tasks:
                    for task_name in explicitly_excluded_tasks:
                        lines.append(f"  - {task_name}: data collection/protocol task only")
                elif inferred_excluded_count > 0:
                    lines.append(
                        f"  - {inferred_excluded_count} data collection/protocol task(s), "
                        "for example 40 Hz stimulation if present in the protocol")
        
        # Add channel and sample rate info
        n_channels = session_info.get('n_channels', 64)
        sample_rate = session_info.get('sample_rate', 500)
        lines.append(f"System: {n_channels}-channel EEG @ {sample_rate} Hz")
        lines.append("")
        
        # ===== PROFILE SUITABILITY GATE =====
        suitability, suit_reasons, suit_warnings = \
            Enhanced64ChannelReportGenerator._compute_profile_suitability(results, excluded_tasks)

        lines.append("=" * 72)
        lines.append(f"PROFILE SUITABILITY: {suitability}")
        lines.append("=" * 72)
        if suit_reasons:
            lines.append("Blocking reasons:")
            for r in suit_reasons:
                lines.append(f"  - {r}")
        if suit_warnings:
            lines.append("Warnings:")
            for w in suit_warnings:
                lines.append(f"  ! {w}")
        if suitability == "INVALID":
            lines.append("")
            lines.append("Recording does not meet minimum data quality for any analysis use.")
            lines.append("Discard results and recollect with verified electrode contact.")
        elif suitability == "RESEARCH-ONLY":
            lines.append("")
            lines.append("Interpretation scope: Session-level physiological response only.")
            lines.append("Do not generate subject profiles or trait inferences from this session.")
        elif suitability == "PROFILE-READY":
            lines.append("Session meets minimum quality thresholds for subject profiling.")
        lines.append("=" * 72)
        lines.append("")

        # ===== DATA QUALITY VALIDATION =====
        # Check for invalid/unreliable recordings
        data_quality_warnings = []
        is_recording_invalid = False  # Flag for catastrophic quality issues
        
        # Critical: No baseline data
        if baseline_ec == 0 and baseline_eo == 0:
            data_quality_warnings.append("CRITICAL: No baseline data recorded")
            is_recording_invalid = True
        
        # Critical: No task data
        if tasks_executed == 0 and len(per_task) == 0:
            data_quality_warnings.append("CRITICAL: No task data recorded")
            is_recording_invalid = True
        
        # Effect size quality notes (informational only)
        # NOTE: Effect size checks (mean/median |d|) proved unreliable for distinguishing
        # cap-not-worn from legitimate cognitive effects. Both produce median|d|~1-2.
        # Channel quality (poor channel %) is the reliable discriminator.
        # Keep median|d| > 5.0 as a warning; suppression is handled by channel quality gate only.
        # Rationale: Hedges' g is dimensionless — high values can reflect genuine EMG/task
        # activity (e.g. mental_math subvocalization, emotion_face facial muscle activation)
        # in recordings with green impedances. Channel quality (>30% poor) is the reliable
        # discriminator for cap-not-worn. Effect size alone is not sufficient to suppress.
        for task_name, task_data in per_task.items():
            task_summary = task_data.get('summary', {})
            median_d = task_summary.get('effect_size_median', 0)
            if median_d > 5.0:
                data_quality_warnings.append(
                    f"WARNING: Elevated effect sizes in {task_name} (median|d|={median_d:.1f}). "
                    f"Possible EMG/muscle artifact or strong task activation. Interpret with caution."
                )
        
        # Check channel quality from artifact summary
        artifact_summary = results.get('artifact_summary', {})
        channel_quality = artifact_summary.get('channel_quality', {})
        
        # Define regions for coverage check
        region_channels = {
            'frontal': ['Fp1', 'Fp2', 'F7', 'F3', 'Fz', 'F4', 'F8', 'AF7', 'AF3', 'AF4', 'AF8', 'F5', 'F1', 'F2', 'F6', 'F9', 'F10'],
            'central': ['FC5', 'FC1', 'FC2', 'FC6', 'C3', 'C4', 'FC3', 'FCz', 'FC4', 'C5', 'C1', 'C2', 'C6'],
            'temporal': ['T7', 'T8', 'T9', 'T10', 'FT7', 'FT8', 'TP7', 'TP8'],
            'parietal': ['CP5', 'CP1', 'CP2', 'CP6', 'P7', 'P3', 'Pz', 'P4', 'P8', 'CP3', 'CP4', 'P5', 'P1', 'P2', 'P6', 'P9', 'P10'],
            'occipital': ['O1', 'O2', 'PO5', 'PO3', 'PO4', 'PO6', 'PO7', 'PO8', 'POz']
        }
        
        if channel_quality:
            good_channels = sum(1 for q in channel_quality.values() if q >= 0.7)
            poor_channels = sum(1 for q in channel_quality.values() if q < 0.4)
            total_channels = len(channel_quality)
            
            # Check regional coverage
            all_regions_zero = True
            for region_name, region_ch_list in region_channels.items():
                region_good = sum(1 for ch in region_ch_list 
                                 if ch in channel_quality and channel_quality[ch] >= 0.7)
                if region_good > 0:
                    all_regions_zero = False
                    break
            
            # CRITICAL: 0% good channel coverage in ALL regions
            if all_regions_zero:
                data_quality_warnings.append(
                    "CRITICAL: Zero good channels in all brain regions (0% coverage)"
                )
                is_recording_invalid = True
            
            # CRITICAL: >30% poor channels (cap-not-worn detection)
            # Validated: cap-not-worn = 39% poor (CRITICAL), properly worn = 5% (OK)
            if total_channels > 0 and poor_channels / total_channels > 0.30:
                data_quality_warnings.append(
                    f"CRITICAL: High proportion of poor channels ({poor_channels}/{total_channels} channels < 40% quality, {poor_channels/total_channels*100:.0f}%). "
                    f"Headset likely not worn correctly or poor electrode contact."
                )
                is_recording_invalid = True
            # WARNING: 20-30% poor channels
            elif total_channels > 0 and poor_channels / total_channels > 0.20:
                data_quality_warnings.append(
                    f"WARNING: Elevated poor channel count ({poor_channels}/{total_channels} channels < 40% quality, {poor_channels/total_channels*100:.0f}%). "
                    f"Check electrode contact and impedances."
                )
            
            # CRITICAL: Almost no good channels (<10%)
            if total_channels > 0 and good_channels / total_channels < 0.1:
                if not any("Zero good channels" in w for w in data_quality_warnings):
                    data_quality_warnings.append(
                        "CRITICAL: Minimal good channel coverage (headset may not be worn properly)"
                    )
                is_recording_invalid = True
        
        # Check per-task data quality — engine-level warnings are informational only.
        # Effect-size-based "unreliable" flags from the engine do NOT set is_recording_invalid;
        # only channel quality (>30% poor) triggers suppression.
        multi_task = results.get('multi_task_results', {})
        per_task_dq = multi_task.get('per_task', {})
        tasks_with_elevated_effects = 0
        for _tname, _tdata in per_task_dq.items():
            _tdq = _tdata.get('summary', {}).get('data_quality', {})
            if _tdq and not _tdq.get('reliable', True):
                # Only count if the unreliability is NOT already captured by our effect-size check
                if not any(_tname in w for w in data_quality_warnings):
                    tasks_with_elevated_effects += 1
        
        # When force_analysis is set, downgrade invalid → unreliable so results are shown
        if force_analysis and is_recording_invalid:
            is_recording_invalid = False
            if not any('force' in w.lower() for w in data_quality_warnings):
                data_quality_warnings.insert(0,
                    "NOTE: --force flag active. Results shown despite poor data quality. "
                    "Interpret all findings with extreme caution."
                )

        # TOP-LEVEL CRITICAL BANNER (before normal header)
        if is_recording_invalid:
            # Insert critical banner at the top (after header but before baseline counts)
            critical_banner = [
                "",
                "█" * 72,
                "█" + " " * 70 + "█",
                "█" + " " * 16 + "⚠️  CRITICAL DATA QUALITY ALERT  ⚠️" + " " * 16 + "█",
                "█" + " " * 70 + "█",
                "█  RECORDING STATUS: INVALID / UNRELIABLE - CAP LIKELY NOT WORN  " + " " * 6 + "█",
                "█" + " " * 70 + "█",
                "█  NO USABLE EEG DATA - ELECTROMAGNETIC NOISE OR DISCONNECTED CAP" + " " * 3 + "█",
                "█" + " " * 70 + "█",
                "█" * 72,
                ""
            ]
            # Find where to insert (after "System: ..." line)
            for i, line in enumerate(lines):
                if line.startswith("System:"):
                    lines = lines[:i+1] + critical_banner + lines[i+1:]
                    break
        
        # Emit detailed warnings
        if data_quality_warnings:
            lines.append("=" * 72)
            lines.append("⚠️  DATA QUALITY WARNINGS")
            lines.append("=" * 72)
            
            for warning in data_quality_warnings:
                if "CRITICAL" in warning:
                    lines.append(f"🚨 {warning}")
                elif "NOTE:" in warning:
                    lines.append(f"ℹ️  {warning}")
                else:
                    lines.append(f"⚠️  {warning}")
            
            lines.append("")
            
            if is_recording_invalid:
                lines.append("Possible causes:")
                if baseline_ec == 0 and baseline_eo == 0:
                    lines.append("  • Recording interrupted during baseline phase")
                    lines.append("  • Headset disconnected before data collection")
                if tasks_executed == 0:
                    lines.append("  • Tasks not executed or recording stopped prematurely")
                if any("headset may not be worn" in w or "Zero good channels" in w 
                       for w in data_quality_warnings):
                    lines.append("  • EEG cap not placed on head (cap-off recording)")
                    lines.append("  • Recording ran without headset connected")
                    lines.append("  • All electrodes have poor contact / no conductive gel")
                    lines.append("  • Impedances >100 kΩ or open circuit")
                if any("Majority poor channel quality" in w for w in data_quality_warnings):
                    lines.append("  • Catastrophic signal quality across most channels")
                    lines.append("  • Environmental electromagnetic interference")
                
                lines.append("")
                lines.append("⚠️  ANALYSIS RESULTS BELOW ARE UNRELIABLE AND SHOULD BE DISCARDED")
                lines.append("")
                lines.append("Recommendation:")
                lines.append("  1. DO NOT USE these results for any purpose")
                lines.append("  2. Recollect data with proper headset placement")
                lines.append("  3. Verify impedances are < 20 kΩ before starting")
                lines.append("  4. Check electrode gel application and skin contact")
                lines.append("  5. Complete full baseline + task protocol without interruption")
                lines.append("")
            
            lines.append("=" * 72)
            lines.append("")
        
        # ===== PER-TASK STATISTICAL SUMMARIES =====
        if per_task:
            if is_recording_invalid:
                lines.append("[SUPPRESSED - INVALID RECORDING]")
                lines.append("-" * 40)
                lines.append("Per-task statistical summaries suppressed due to invalid data quality.")
                lines.append("See data quality warnings above for details.")
                lines.append("")
            else:
                lines.append("Per-Task Statistical Summaries")
                lines.append("-"*40)
            
            if not is_recording_invalid:
                for task_name in sorted(per_task.keys()):
                    if task_name.lower() in excluded_tasks:
                        continue
                    task_data = per_task[task_name]
                    lines.extend(Enhanced64ChannelReportGenerator._generate_detailed_task_summary(
                        task_name, task_data, n_permutations, force_analysis=force_analysis,
                        session_invalid=is_recording_invalid))
        
        # ===== CROSS-TASK FAMILY-WISE ERROR CORRECTION =====
        cross_task_correction = multi_task.get('cross_task_correction', {})
        if cross_task_correction and cross_task_correction.get('n_tasks', 0) >= 2:
            lines.append("")
            lines.append("Cross-Task Family-Wise Error Correction")
            lines.append("-"*45)
            lines.append(f"  Method: {cross_task_correction.get('method', 'Holm-Bonferroni')}")
            lines.append(f"  Tasks compared: {cross_task_correction.get('n_tasks', 0)}")
            lines.append(f"  Family-wise alpha: {cross_task_correction.get('alpha', 0.05)}")
            lines.append("")
            lines.append("  Per-Task Omnibus Results (FWER-corrected):")
            raw_pvals = cross_task_correction.get('raw_pvals', {})
            adj_pvals = cross_task_correction.get('adjusted_pvals', {})
            sig_tasks = cross_task_correction.get('significant_tasks', [])
            displayed_sig_tasks = [
                task_name for task_name in sig_tasks
                if str(task_name).lower() not in excluded_tasks
            ]
            displayed_raw_pvals = []
            for task_name in sorted(raw_pvals.keys()):
                if task_name.lower() in excluded_tasks:
                    continue
                raw_p = raw_pvals.get(task_name, 1.0)
                adj_p = adj_pvals.get(task_name, 1.0)
                sig_marker = " [SIGNIFICANT*]" if task_name in sig_tasks else ""
                if isinstance(raw_p, (int, float)):
                    displayed_raw_pvals.append(float(raw_p))
                raw_p_str = "<1e-300" if raw_p < 1e-300 else f"{raw_p:.6g}"
                adj_p_str = "<1e-300" if adj_p < 1e-300 else f"{adj_p:.6g}"
                lines.append(f"    {task_name}: task_omnibus_p={raw_p_str} -> adjusted_p={adj_p_str}{sig_marker}")
            lines.append("")
            if displayed_sig_tasks:
                lines.append("  * Significant after family-wise error correction")
            else:
                lines.append("  No task-level omnibus effects survived Holm-Bonferroni family-wise correction.")
                if displayed_raw_pvals and all(abs(p - 1.0) < 1e-12 for p in displayed_raw_pvals):
                    lines.append("  No reliable between-task differentiation was detected.")
            lines.append("")
        
        # ===== COMBINED TASK AGGREGATE =====
        combined = multi_task.get('combined', {})
        if combined:
            lines.append("")
            lines.append("Combined Task Aggregate")
            lines.append("-"*30)
            lines.extend(Enhanced64ChannelReportGenerator._generate_combined_summary(combined))
        
        # ===== ACROSS-TASK OMNIBUS =====
        # Note: The engine returns 'across_task' not 'omnibus'
        across_task = multi_task.get('across_task', multi_task.get('omnibus', {}))
        if across_task:
            lines.append("")
            lines.append("Across-Task Omnibus (Feature Stability)")
            lines.append("-"*40)
            suppress_gamma_for_profile = any(
                tdata.get('summary', {}).get('gamma_flood', {}).get('detected', False)
                for tname, tdata in per_task.items()
                if tname.lower() not in excluded_tasks
            )
            lines.extend(Enhanced64ChannelReportGenerator._generate_omnibus_summary(
                across_task, suppress_gamma=suppress_gamma_for_profile))
        
        # ===== 64-CHANNEL SPECIFIC ANALYSIS =====
        lines.append("")
        lines.append("64-Channel Spatial & Connectivity Analysis")
        lines.append("="*72)
        
        # Extract combined per-feature dict for multichannel summary.
        # combined['analysis'] wraps {per_feature, omnibus, summary}; the spatial
        # report needs the inner per_feature mapping (feature_name -> stats).
        combined_analysis_parent = combined.get('analysis', {}) if combined else {}
        combined_per_feature = combined_analysis_parent.get('per_feature', combined_analysis_parent)
        
        lines.extend(Enhanced64ChannelReportGenerator._generate_multichannel_summary(
            results, combined_per_feature, suitability=suitability))
        
        # ===== CONFIGURATION & PROVENANCE =====
        lines.append("")
        lines.append("Configuration & Provenance")
        lines.append("-"*40)
        mode_str = "FAST" if fast_mode else "FULL"
        lines.append(f"Mode={mode_str} | alpha=0.05 | dependence=independence approximation")
        
        # Permutation testing details
        if not fast_mode:
            pval_resolution = 1.0 / (n_permutations + 1)
            lines.append(f"Permutation testing: n_perm={n_permutations} (block-level SumP, p-value resolution: {pval_resolution:.4f})")
        else:
            lines.append("Permutation testing: Disabled (parametric tests only)")
        
        lines.append("Effect measure: delta | Discretization bins: 5 | FDR alpha: 0.05")
        lines.append("Multi-channel: 64-channel EEG (10-20 extended system)")
        lines.append("Baseline: eyes-closed only (eyes-open retained for reference, not pooled).")
        lines.append(
            "Profile limitation: eyes-open cognitive/visual tasks should prefer eyes-open "
            "or task-specific pre-task baselines; EC-only task contrasts are lower confidence "
            "for profiling.")
        lines.append("")
        
        # Preprocessing configuration (from config object if available)
        lines.append("Preprocessing Applied:")
        artifact_summary = results.get('artifact_summary', {})
        hf_rejection = artifact_summary.get('hf_artifact_rejection', {})
        advanced_emg = artifact_summary.get('advanced_emg_cleaning', {})
        if config is not None:
            # Line noise filtering
            line_freq = getattr(config, 'line_noise_freq', 60.0)
            apply_notch = getattr(config, 'apply_notch_filter', True)
            if apply_notch:
                lines.append(f"  - Notch filter: {line_freq} Hz + harmonics (Q=30)")
            else:
                lines.append("  - Notch filter: Disabled")
            
            # EMG threshold mode
            emg_adaptive = getattr(config, 'emg_adaptive_threshold', True)
            emg_fixed = getattr(config, 'emg_fixed_ratio', 1.5)
            if emg_adaptive:
                lines.append(f"  - EMG threshold: Adaptive (baseline_mean + 2xSD)")
            else:
                lines.append(f"  - EMG threshold: Fixed ratio > {emg_fixed}")
            
            # Bootstrap CI
            compute_ci = getattr(config, 'compute_bootstrap_ci', True)
            n_boot = getattr(config, 'n_boot', getattr(config, 'bootstrap_ci_samples', 1000))
            if compute_ci:
                lines.append(f"  - Bootstrap 95% CI: {n_boot} iterations (percentile method)")
            else:
                lines.append("  - Bootstrap 95% CI: Disabled")
            
            # Block parameters
            block_sec = getattr(config, 'block_seconds', 4.0)
            min_blocks = getattr(config, 'min_blocks_per_condition', 8)
            lines.append(f"  - Block aggregation: {block_sec}s blocks (min {min_blocks} per condition)")
        else:
            # Default descriptions when no config available
            lines.append("  - Notch filter: 60 Hz + harmonics (Q=30)")
            lines.append("  - EMG threshold: Adaptive (baseline_mean + 2xSD)")
            lines.append("  - Bootstrap 95% CI: 1000 iterations (percentile method)")
            lines.append("  - Block aggregation: 4.0s blocks (min 8 per condition)")
        lines.append("  - Average reference: Applied")
        if hf_rejection:
            if hf_rejection.get('enabled', False):
                tested = int(hf_rejection.get('windows_tested', 0) or 0)
                rejected = int(hf_rejection.get('windows_rejected', 0) or 0)
                forced = int(hf_rejection.get('forced_retained_windows', 0) or 0)
                pct = (rejected / tested * 100.0) if tested else 0.0
                lines.append(
                    f"  - High-frequency epoch rejection: {rejected}/{tested} windows rejected "
                    f"({pct:.1f}%, method={hf_rejection.get('method', 'adaptive_hf_ratio')}, "
                    f"forced retained={forced})")
                saturated = int(hf_rejection.get('saturated_phases', 0) or 0)
                if saturated:
                    candidate = int(hf_rejection.get('candidate_rejected', rejected) or 0)
                    lines.append(
                        f"    Saturation guard: {saturated} phase(s) treated as tonically contaminated; "
                        f"{candidate} candidate windows were not dropped to avoid biased tiny-sample analysis.")
            else:
                lines.append("  - High-frequency epoch rejection: Disabled")
        if advanced_emg:
            def _advanced_line(label, key_prefix):
                requested = bool(advanced_emg.get(f'{key_prefix}_requested', False))
                applied = bool(advanced_emg.get(f'{key_prefix}_applied', False))
                available = bool(advanced_emg.get(f'{key_prefix}_available', False))
                if applied:
                    status = "applied"
                elif requested:
                    status = "requested, not applied" if not available else "requested, pending implementation"
                else:
                    status = "not requested"
                lines.append(f"  - {label}: {status}")

            _advanced_line("ICA EMG cleaning", "ica")
            _advanced_line("CSD transform", "csd")
            _advanced_line("CCA EMG cleaning", "cca")
        lines.append("")
        
        lines.append("Phase-Based Recording:")
        lines.append("  • Only phases marked 'record=True' in task definitions are processed")
        lines.append("  • Cognitive tasks (mental_math, etc.): Record only 'task' phase (52s)")
        lines.append("  • Protocol tasks (diverse_thinking, reappraisal): Record 'thinking' phases (30s)")
        lines.append("  • Visual tasks (curiosity, num_form): Record 'viewing'/'video' phases")
        lines.append("  • Continuous tasks (emotion_face): Record all phases")
        lines.append("  • Preparation phases ('get_ready', 'cue') excluded from analysis")
        lines.append("")
        
        # ===== GLOSSARY =====
        lines.append("Glossary of Metrics")
        lines.append("-"*40)
        lines.append("Fisher: Fisher combined p-value using an independence approximation; interpret cautiously for correlated EEG features")
        if fast_mode:
            lines.append("SumP: Sum of per-feature p-values; analytic approximation used in FAST mode")
        else:
            lines.append("SumP: Sum of per-feature p-values; permutation p-value gauges deviation from baseline")
        lines.append("CompositeScore: Sum of -log10 adjusted p-values as an aggregate strength indicator")
        lines.append("Mean|d|: Mean absolute Cohen's d effect size across significant features")
        lines.append("perm_p: Permutation-derived significance comparing observed statistic to shuffled baseline")
        lines.append("perm_used: Indicates whether permutations (vs analytic approximation) were applied")
        lines.append("fisher_df: Degrees of freedom used in Fisher's chi-square approximation")
        lines.append("sig_feature_count: Number of features passing the FDR threshold when feature selection enabled")
        lines.append("sig_prop: Proportion of tested features that remained significant after FDR control")
        lines.append("omnibus_stat: Across-task Friedman/Wilcoxon statistic measuring feature variation between tasks")
        lines.append("omnibus_p: P-value for omnibus_stat before FDR adjustment")
        lines.append("omnibus_q: FDR-adjusted p-value for the across-task omnibus test")
        lines.append("omnibus_sig: True when omnibus_q is below the configured FDR alpha")
        lines.append("posthoc_q: Pairwise task comparison FDR-adjusted q-values (matrix form in exports)")
        lines.append("Δ: Absolute difference between task and baseline means for the feature")
        lines.append("d: Cohen's d effect size comparing task vs baseline distributions")
        lines.append("ratio: Task mean divided by baseline mean (signed) for quick proportional change")
        lines.append("bin: Discretized effect bin index relative to baseline distribution quantiles")
        
        return lines

    @staticmethod
    def _extract_per_feature(task_data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        analysis_parent = task_data.get('analysis', {})
        return analysis_parent.get('per_feature', analysis_parent) or {}

    @staticmethod
    def _feature_is_profile_safe(feat_name: str, feat_data: Dict[str, Any],
                                 suppress_gamma: bool = False) -> bool:
        """True when a feature can appear in profile-facing report sections."""
        if not isinstance(feat_data, dict):
            return False
        if feat_data.get('artifact_suspect', False):
            return False
        if feat_data.get('emg_excluded', False):
            return False
        if suppress_gamma and 'gamma' in str(feat_name).lower():
            return False
        return True

    @staticmethod
    def _compute_profile_suitability(results: Dict[str, Any], excluded_tasks: set) -> tuple:
        """
        Evaluate whether this session is suitable for subject profiling.

        Returns
        -------
        suitability : str
            "PROFILE-READY", "RESEARCH-ONLY", or "INVALID"
        reasons : list[str]
            Human-readable reasons for the rating (empty when PROFILE-READY)
        warnings : list[str]
            Soft warnings that do not block profiling on their own
        """
        multi_task = results.get('multi_task_results', {})
        per_task = multi_task.get('per_task', {})
        across_task = multi_task.get('across_task', multi_task.get('omnibus', {}))

        reasons = []
        warnings = []

        # --- Gamma EMG flood ---
        flood_tasks = []
        for tname, tdata in per_task.items():
            if tname.lower() in excluded_tasks:
                continue
            gamma_info = tdata.get('summary', {}).get('gamma_flood', {})
            flood_detected = gamma_info.get('detected', gamma_info.get('flood_detected', False))
            if flood_detected:
                sig_fraction = gamma_info.get('sig_fraction', gamma_info.get('gamma_sig_pct'))
                if sig_fraction is None:
                    total_gamma = gamma_info.get('total_gamma', 0) or 0
                    sig_gamma = gamma_info.get('sig_gamma', 0) or 0
                    sig_fraction = sig_gamma / total_gamma if total_gamma else 0
                pct = sig_fraction * 100
                flood_tasks.append(f"{tname} ({pct:.0f}%)")
        if flood_tasks:
            reasons.append(
                f"Gamma EMG flood in {len(flood_tasks)} task(s): {', '.join(flood_tasks)}")

        # --- Artifact-suspect feature count ---
        total_artifact_suspect = sum(
            tdata.get('summary', {}).get('artifact_suspect_count', 0)
            for tname, tdata in per_task.items()
            if tname.lower() not in excluded_tasks
        )
        artifact_feature_names = set()
        artifact_instances = 0
        fallback_artifact_count = int(total_artifact_suspect or 0)
        for tname, tdata in per_task.items():
            if tname.lower() in excluded_tasks:
                continue
            for feat_name, feat_data in Enhanced64ChannelReportGenerator._extract_per_feature(tdata).items():
                if isinstance(feat_data, dict) and feat_data.get('artifact_suspect', False):
                    artifact_instances += 1
                    artifact_feature_names.add(feat_name)

        if artifact_instances == 0 and fallback_artifact_count > 0:
            artifact_instances = fallback_artifact_count

        if artifact_instances > 20:
            if artifact_feature_names:
                artifact_text = (
                    f"{len(artifact_feature_names)} unique feature names / "
                    f"{artifact_instances} task-feature instances with |d| > 10")
            else:
                artifact_text = f"{artifact_instances} task-feature instances with |d| > 10"
            reasons.append(
                f"Artifact-suspect features: {artifact_text} - "
                f"likely movement or electrode artifact")

        # --- HF saturation guard ---
        artifact_summary = results.get('artifact_summary', {})
        hf_rejection = artifact_summary.get('hf_artifact_rejection', {})
        saturated_phases = int(hf_rejection.get('saturated_phases', 0) or 0)
        candidate_windows = int(hf_rejection.get('candidate_rejected', 0) or 0)
        if saturated_phases > 0:
            if candidate_windows > 0:
                reasons.append(
                    f"High-frequency saturation guard activated in {saturated_phases} phase(s): "
                    f"{candidate_windows} candidate windows left in place to avoid biased tiny-sample analysis")
            else:
                reasons.append(
                    f"High-frequency saturation guard activated in {saturated_phases} phase(s): "
                    "epoch rejection disabled for tonically contaminated phases")

        # --- Expectation-alignment: count Grade D tasks ---
        grade_d_tasks = []
        grade_info = {}
        for tname, tdata in per_task.items():
            if tname.lower() in excluded_tasks:
                continue
            grade = tdata.get('summary', {}).get('expectation', {}).get('grade', '')
            grade_info[tname] = grade
            if grade == 'D':
                grade_d_tasks.append(tname)
        if len(grade_d_tasks) > 0:
            reasons.append(
                f"Expectation-alignment grade D in {len(grade_d_tasks)}/{len(grade_info)} task(s): "
                f"{', '.join(grade_d_tasks)}")

        # --- Across-task feature saturation (>85% significant = critical) ---
        sat_threshold = 0.85
        features = across_task.get('features', {})
        if features:
            sig_count = sum(1 for v in features.values() if v.get('omnibus_sig', False))
            total_count = len(features)
            sat_ratio = sig_count / total_count if total_count > 0 else 0
            if sat_ratio > sat_threshold:
                reasons.append(
                    f"Across-task feature saturation: {sig_count}/{total_count} "
                    f"({sat_ratio*100:.0f}%) features significant — above {sat_threshold*100:.0f}% "
                    f"critical threshold (pipeline non-specific)")

        # --- Channel quality: INVALID recording ---
        artifact_summary = results.get('artifact_summary', {})
        channel_quality = artifact_summary.get('channel_quality', {})
        if channel_quality:
            total_ch = len(channel_quality)
            poor_ch = sum(1 for q in channel_quality.values() if q < 0.4)
            good_ch = sum(1 for q in channel_quality.values() if q >= 0.7)
            if total_ch > 0 and poor_ch / total_ch > 0.30:
                reasons.append(
                    f"Recording INVALID: {poor_ch}/{total_ch} channels poor quality "
                    f"({poor_ch/total_ch*100:.0f}%) — cap likely not worn correctly")
            elif total_ch > 0 and good_ch / total_ch < 0.10:
                reasons.append(
                    f"Recording INVALID: only {good_ch}/{total_ch} good channels "
                    f"({good_ch/total_ch*100:.0f}%) — insufficient electrode contact")

        # --- Occipital coverage ---
        occ_channels = ['O1', 'O2', 'Oz', 'PO3', 'PO4', 'PO7', 'PO8', 'POz']
        if channel_quality:
            occ_good = sum(1 for ch in occ_channels
                           if ch in channel_quality and channel_quality[ch] >= 0.7)
            occ_total = sum(1 for ch in occ_channels if ch in channel_quality)
            if occ_total > 0 and occ_good / occ_total < 0.4:
                warnings.append(
                    f"Occipital coverage: {occ_good}/{occ_total} good channels "
                    f"({occ_good/occ_total*100:.0f}%) — visual/occipital inferences unreliable")

        if reasons:
            # Escalate to INVALID if channel quality is the primary cause
            if any('Recording INVALID' in r for r in reasons):
                suitability = "INVALID"
            else:
                suitability = "RESEARCH-ONLY"
        else:
            suitability = "PROFILE-READY"

        return suitability, reasons, warnings

    @staticmethod
    def _generate_detailed_task_summary(task_name: str, task_data: Dict[str, Any], n_perm: int,
                                        force_analysis: bool = False,
                                        session_invalid: bool = False) -> List[str]:
        """Generate detailed task summary matching single-channel format."""
        lines = []
        lines.append("")
        lines.append(f"[{task_name}]")
        
        summary = task_data.get('summary', {})
        fisher = summary.get('fisher', {})
        sum_p = summary.get('sum_p', {})
        feature_sel = summary.get('feature_selection', {})
        ess_info = summary.get('ess', {})
        composite_info = summary.get('composite', {})
        expectation = summary.get('expectation', {})
        # analysis contains {'per_feature': {...}, 'omnibus': {...}, 'summary': {...}}
        # We need the per_feature dict which has actual feature names as keys
        analysis_parent = task_data.get('analysis', {})
        analysis = analysis_parent.get('per_feature', {})
        gamma_flood_info = summary.get('gamma_flood', {})
        gamma_flood_detected = gamma_flood_info.get('detected', gamma_flood_info.get('flood_detected', False))
        
        # ==================================================================
        # DATA QUALITY CHECK - Prominently display any reliability warnings
        # ==================================================================
        data_quality = summary.get('data_quality', {})
        if data_quality and not data_quality.get('reliable', True) and not force_analysis and session_invalid:
            lines.append("")
            lines.append("  " + "*" * 30)
            lines.append("  DATA QUALITY WARNING - RESULTS UNRELIABLE")
            lines.append("  " + "*" * 30)
            for warning in data_quality.get('warnings', []):
                # Wrap long warnings
                wrapped = [warning[i:i+70] for i in range(0, len(warning), 70)]
                for w in wrapped:
                    lines.append(f"    {w}")
            lines.append("")
            lines.append("  [!] These results should NOT be interpreted as valid EEG analysis.")
            sig_prop = data_quality.get('sig_prop', 0)
            sig_count = data_quality.get('sig_count', 0)
            total = data_quality.get('total_features', 0)
            lines.append(f"     Significant: {sig_count}/{total} ({sig_prop*100:.1f}% - expected <30% for real data)")
            lines.append("  " + "⚠" * 30)
            lines.append("")
        elif data_quality and data_quality.get('warnings') and not force_analysis and session_invalid:
            lines.append("")
            lines.append("  NOTICE: DATA QUALITY NOTICE:")
            for warning in data_quality.get('warnings', []):
                lines.append(f"    {warning}")
            lines.append("")
        
        # Fisher correlation metadata. The offline engine currently uses an
        # independence approximation, so do not label this as a KM correction.
        total_features = fisher.get('k_features', feature_sel.get('total_features', len(analysis)))
        km_corr = fisher.get('km_mean_r', 0.0)
        km_df = fisher.get('km_df', total_features * 2.0)
        km_df_ratio = fisher.get('km_df_ratio', km_df/(2*max(total_features,1)))
        lines.append(f"  Fisher correlation guard: k={total_features}, mean_offdiag_r={km_corr:.6f}, df/(2k)={km_df_ratio:.6f}")
        
        # Fisher combined p-value - match actual structure
        fisher_p = fisher.get('km_p', 1.0)
        fisher_sig = fisher.get('significant', False)
        fisher_df = fisher.get('km_df', 0.0)
        if isinstance(fisher_p, (int, float)) and fisher_p < 1e-300:
            fisher_p_str = "<1e-300"
        elif isinstance(fisher_p, (int, float)):
            fisher_p_str = f"{fisher_p:.6g}"
        else:
            fisher_p_str = str(fisher_p)
        lines.append(f"  Fisher_p={fisher_p_str} sig={fisher_sig} df={fisher_df:.4f} method=independence_approximation")
        
        # ESS (Effective Sample Size) from actual task_summary
        baseline_blocks = ess_info.get('baseline_blocks', 4)
        task_blocks = ess_info.get('task_blocks', 4)
        n_blocks = max(baseline_blocks or 4, task_blocks or 4)
        lines.append(f"  ESS: baseline={baseline_blocks}, task={task_blocks}, n_blocks={n_blocks}")
        
        # SumP - match actual structure
        sum_p_obs = sum_p.get('value', sum_p.get('observed_sum', 0.0))
        sum_p_pval = sum_p.get('perm_p', sum_p.get('chi2_p', 'N/A'))
        sum_p_sig = sum_p.get('significant', False)
        perm_used = sum_p.get('permutation_used', False)
        if isinstance(sum_p_pval, (int, float)):
            sum_p_pval_str = f"{sum_p_pval:.6f}" if sum_p_pval > 0.000001 else f"{sum_p_pval:.6g}"
        else:
            sum_p_pval_str = str(sum_p_pval)
        lines.append(f"  SumP={sum_p_obs:.4f} p={sum_p_pval_str} sig={sum_p_sig} perm={perm_used} method={'permutation' if perm_used else 'parametric(Irwin-Hall)'}")
        
        # CompositeScore and Mean|d| - use actual structure
        composite = composite_info.get('score', summary.get('composite_score', 0.0))
        mean_d = summary.get('effect_size_mean', 0.0)
        median_d = summary.get('effect_size_median', 0.0)
        artifact_suspect_n = summary.get('artifact_suspect_count', 0)
        winsor_note = f" [Mean|d| Winsorised: {artifact_suspect_n} features capped at |d|=10]" if artifact_suspect_n > 0 else ""
        lines.append(f"  CompositeScore={composite:.3f} Mean|d|={mean_d:.6f} Median|d|={median_d:.6f}{winsor_note}")
        
        # Decision thresholds - get from fisher alpha
        alpha = fisher.get('alpha', 0.05)
        fdr_alpha = feature_sel.get('fdr_alpha', 0.05) if feature_sel else 0.05
        lines.append(f"  Decision thresholds (band-specific): p≤{alpha}, q≤{fdr_alpha}")
        lines.append("    Effect sizes: α≥0.25, β≥0.35, γ≥0.30, θ≥0.30, ratios≥0.30")
        lines.append("    Percent change: relative features≥5%, absolute≥10%")
        
        # Correlation guard factor
        if total_features > 0:
            m_eff = total_features / max(1 + km_corr * (total_features - 1), 1)
            guard_factor = m_eff / total_features
            lines.append(f"  Correlation guard factor={guard_factor:.5f} (m_eff={m_eff:.4f}/{total_features})")
        
        # Significant Features (top 5 with 95% CI for Cohen's d)
        if analysis:
            # Note: engine stores 'significant', 'hedges_g', 'g_ci_lower/upper'
            all_sig = [(k, v) for k, v in analysis.items() if v.get('significant') or v.get('significant_change')]
            # Partition: clean vs artifact-suspect (|d|>10)
            clean_sig = [
                (k, v) for k, v in all_sig
                if Enhanced64ChannelReportGenerator._feature_is_profile_safe(
                    k, v, suppress_gamma=gamma_flood_detected)
            ]
            artifact_sig = [(k, v) for k, v in all_sig if v.get('artifact_suspect', False)]
            # Sort clean features by q-value ascending (strongest statistical evidence first)
            clean_sig.sort(key=lambda x: x[1].get('q_value', x[1].get('p_value', 1.0)))

            lines.append(
                "  Significant Features (top 5 by q-value, artifact-suspect/EMG-excluded excluded):")
            for feat_name, feat_data in clean_sig[:5]:
                p = feat_data.get('p_value', 1.0)
                q = feat_data.get('q_value', p)
                task_mean = feat_data.get('task_mean', 0.0)
                base_mean = feat_data.get('baseline_mean', 0.0)
                delta = feat_data.get('delta', task_mean - base_mean)
                d = feat_data.get('hedges_g', feat_data.get('effect_size_d', 0.0))
                d_ci_lo = feat_data.get('g_ci_lower', feat_data.get('d_ci_lower', np.nan))
                d_ci_hi = feat_data.get('g_ci_upper', feat_data.get('d_ci_upper', np.nan))

                p_str = "0" if p == 0 else f"{p:.6g}"
                q_str = (f"{q:.3g}" if q > 0 else "0") if (q == 0 or q < 1e-299) else f"{q:.6g}"
                ci_str = (f" 95%CI=[{d_ci_lo:+.3f},{d_ci_hi:+.3f}]"
                          if not np.isnan(d_ci_lo) and not np.isnan(d_ci_hi) else "")
                gamma_warn = " [GAMMA: EMG caution]" if 'gamma' in feat_name.lower() else ""

                lines.append(f"    {feat_name}: p={p_str} q={q_str} d={d:+.5f}{ci_str} delta={delta:+.6f}{gamma_warn}")

            if artifact_sig:
                artifact_sig.sort(key=lambda x: abs(x[1].get('hedges_g', 0)), reverse=True)
                lines.append(f"  Artifact-suspect features (|d|>10, {len(artifact_sig)} total; top 3):")
                for feat_name, feat_data in artifact_sig[:3]:
                    d = feat_data.get('hedges_g', 0.0)
                    p = feat_data.get('p_value', 1.0)
                    p_str = "0" if p == 0 else f"{p:.6g}"
                    lines.append(f"    {feat_name}: d={d:+.5f} p={p_str} [likely movement/electrode artifact]")

            # Top 5 Features by p-value (profile-facing artifact exclusions applied)
            clean_all = [
                (k, v) for k, v in analysis.items()
                if Enhanced64ChannelReportGenerator._feature_is_profile_safe(
                    k, v, suppress_gamma=gamma_flood_detected)
            ]
            clean_all.sort(key=lambda x: x[1].get('p_value', 1.0))

            lines.append("  Top 5 Features (by p-value, artifact-suspect/EMG-excluded excluded):")
            for feat_name, feat_data in clean_all[:5]:
                p = feat_data.get('p_value', 1.0)
                q = feat_data.get('q_value', p)
                sig = feat_data.get('significant') or feat_data.get('significant_change', False)
                task_mean = feat_data.get('task_mean', 0.0)
                base_mean = feat_data.get('baseline_mean', 1.0)
                delta = feat_data.get('delta', task_mean - base_mean)
                d = feat_data.get('hedges_g', feat_data.get('effect_size_d', 0.0))
                ratio = task_mean / base_mean if base_mean != 0 else 0.0

                p_str = "0" if p == 0 else f"{p:.6g}"
                q_str = (f"{q:.3g}" if q > 0 else "0") if (q == 0 or q < 1e-299) else f"{q:.6g}"

                lines.append(f"    {feat_name}: p={p_str} q={q_str} sig={sig} delta={delta:+.6f} d={d:+.5f} ratio={ratio:.6f}")
            
            # ==================================================================
            # GAMMA BAND RELIABILITY WARNING
            # Gamma (>30 Hz) is susceptible to EMG contamination and should be 
            # interpreted with caution when significant effects are observed.
            # ==================================================================
            gamma_sig_features = [f for f, v in all_sig if 'gamma' in f.lower()]
            if gamma_sig_features:
                lines.append("")
                lines.append("  --- GAMMA BAND RELIABILITY WARNING ---")
                if gamma_flood_detected:
                    n_gamma = gamma_flood_info.get('total_gamma', len(gamma_sig_features))
                    n_sig = gamma_flood_info.get('sig_gamma', len(gamma_sig_features))
                    pct = gamma_flood_info.get('sig_fraction', 0) * 100
                    thresh_pct = gamma_flood_info.get('threshold', 0.25) * 100
                    lines.append(f"  EMG FLOOD DETECTED: {n_sig}/{n_gamma} gamma features significant "
                                 f"({pct:.0f}% > {thresh_pct:.0f}% threshold).")
                    lines.append("  Broadband muscle artifact is the most likely explanation.")
                    lines.append("  All gamma features EXCLUDED from omnibus statistics")
                    lines.append("  (CompositeScore, Mean|d|, Fisher, SumP recalculated without gamma).")
                else:
                    lines.append("  Significant gamma features detected. Scalp EEG gamma (>30 Hz) is")
                    lines.append("  highly susceptible to muscle artifact (EMG) contamination.")
                lines.append("  Consider these results as secondary outcomes requiring:")
                lines.append("    - Subject verification of minimal jaw clenching during task")
                lines.append("    - Laplacian/CSD transform for spatial filtering (if available)")
                lines.append("    - Source localization to confirm cortical origin")
                lines.append(f"  Gamma features: {', '.join(gamma_sig_features[:5])}")
                if len(gamma_sig_features) > 5:
                    lines.append(f"    ... and {len(gamma_sig_features) - 5} more")
                if gamma_flood_detected:
                    gamma_diag = sorted(
                        [(f, v) for f, v in analysis.items() if 'gamma' in f.lower()],
                        key=lambda x: x[1].get('p_value', 1.0)
                    )
                    lines.append("  EMG-excluded gamma diagnostics (not profile-facing; top 5 by p-value):")
                    for feat_name, feat_data in gamma_diag[:5]:
                        p = feat_data.get('p_value', 1.0)
                        d = feat_data.get('hedges_g', feat_data.get('effect_size_d', 0.0))
                        p_str = "0" if p == 0 else f"{p:.6g}"
                        lines.append(f"    {feat_name}: p={p_str} d={d:+.5f}")
                lines.append("")
            
            # Expectation-Alignment Analysis
            lines.append("  --- Expectation-Alignment Analysis ---")
            # Pass the engine-computed expectation data if available
            expectation_data = summary.get('expectation', {})
            lines.extend(Enhanced64ChannelReportGenerator._generate_expectation_alignment(
                task_name, analysis, all_sig, expectation_data))
        
        return lines
    
    @staticmethod
    def _generate_expectation_alignment(task_name: str, analysis: Dict, sig_features: List,
                                        expectation_data: Optional[Dict] = None) -> List[str]:
        """Generate expectation-alignment analysis using engine-computed data when available."""
        lines = []
        
        # If we have pre-computed expectation data from engine, use it
        if expectation_data and expectation_data.get('grade'):
            grade = expectation_data.get('grade', 'N/A')
            lines.append(f"  Grade: {grade}")
            
            # Counter-directional warning
            if expectation_data.get('counter_directional'):
                lines.append("  WARNING: Counter-directional: >=70% of features moved opposite to task expectations")
            
            # Passed features with full details
            passed = expectation_data.get('passes', [])
            lines.append(f"  Passed Features (n={len(passed)}):")
            if passed:
                for feat in passed[:15]:
                    feat_name = feat.get('feature', 'unknown')
                    direction = feat.get('direction', '?')
                    d_val = feat.get('d')
                    pct = feat.get('pct')
                    p_dir = feat.get('p_dir')
                    rule = feat.get('rule', 'p')
                    
                    info = f"{feat_name} ({direction})"
                    if d_val is not None and not np.isnan(d_val):
                        info += f": Δ%={pct:+.4f}" if pct else ""
                        if p_dir is not None:
                            if p_dir == 0:
                                info += ", p_dir=0"
                            else:
                                info += f", p_dir={p_dir:.6g}"
                        info += f" | rule={rule}"
                    lines.append(f"    {info}")
            else:
                lines.append("    (none)")
            
            # Top Drivers — exclude artifact-suspect features (|d|>10)
            drivers = expectation_data.get('top_drivers', [])
            clean_drivers = [dr for dr in drivers
                             if abs(dr.get('d', 0)) <= 10.0]
            lines.append("  Top Drivers (by |d|, artifact-suspect excluded):")
            if clean_drivers:
                for driver in clean_drivers[:3]:
                    feat_name = driver.get('feature', 'unknown')
                    d_val = driver.get('d', 0)
                    lines.append(f"    {feat_name}: |d|={d_val:.6f}")
            else:
                lines.append("    (none)")
            
            # Notes
            notes = expectation_data.get('notes', [])
            if notes:
                lines.append("  Notes:")
                for note in notes[:5]:
                    lines.append(f"    {note}")
            
            return lines
        
        # Fallback: compute from analysis (simplified version)
        # Define expected patterns
        task_expectations = {
            'attention_focus': {'up': ['beta', 'gamma'], 'down': ['alpha', 'theta']},
            'mental_math': {'up': ['beta', 'gamma', 'frontal'], 'down': ['alpha']},
            'visual_imagery': {'up': ['alpha', 'occipital'], 'down': ['beta']},
            'emotion': {'up': ['frontal_alpha', 'asymmetry'], 'down': []},
            'working_memory': {'up': ['theta', 'beta'], 'down': ['alpha']},
            'cognitive_load': {'up': ['theta'], 'down': ['alpha']},
            '40hz_stimulation': {'up': ['gamma', '40'], 'down': []},  # Gamma entrainment
            'gamma_entrainment': {'up': ['gamma', '40'], 'down': []},
            'meditation': {'up': ['alpha', 'theta'], 'down': ['beta', 'gamma']},
            'relaxation': {'up': ['alpha'], 'down': ['beta', 'gamma']},
        }
        
        expectations = task_expectations.get(task_name, {'up': [], 'down': []})
        
        # Check alignment
        passed_features = []
        for feat_name, feat_data in sig_features:
            task_mean = feat_data.get('task_mean', 0.0)
            base_mean = feat_data.get('baseline_mean', 1.0)
            delta = feat_data.get('delta', task_mean - base_mean)  # Compute if not present
            d = feat_data.get('hedges_g', feat_data.get('effect_size_d', 0.0))
            p = feat_data.get('p_value', 1.0)
            
            # Check if matches expectations
            expected_up = any(exp in feat_name.lower() for exp in expectations['up'])
            expected_down = any(exp in feat_name.lower() for exp in expectations['down'])
            
            if (expected_up and delta > 0) or (expected_down and delta < 0):
                direction = "up" if delta > 0 else "down"
                pct_change = ((task_mean - base_mean) / base_mean * 100) if base_mean != 0 else 0
                # Asymmetry/log-ratio features have baselines near zero, which
                # makes Δ% mathematically unstable and visually misleading
                # (e.g. +2000% for a log-asymmetry shift of 0.05). Suppress
                # Δ% for those families and rely on absolute Δ + d.
                suppress_pct = (
                    feat_name.lower().startswith('asym_')
                    or 'asymmetry' in feat_name.lower()
                    or feat_name.lower().endswith('_relative')
                    or '_ratio' in feat_name.lower()
                )
                
                feat_info = f"{feat_name} ({direction})"
                if abs(d) >= 0.2:
                    feat_info += f": d={d:+.6f}"
                if abs(pct_change) >= 5 and not suppress_pct:
                    feat_info += f", Δ%={pct_change:+.4f}"
                if p == 0:
                    feat_info += f", p_dir=0"
                else:
                    feat_info += f", p_dir={p:.6g}"
                feat_info += " | rule=p"
        
        # Calculate grade
        total_sig = len(sig_features)
        passed = len(passed_features)
        if total_sig > 0:
            alignment_pct = passed / total_sig * 100
            if alignment_pct >= 80:
                grade = "A"
            elif alignment_pct >= 60:
                grade = "B"
            elif alignment_pct >= 40:
                grade = "C"
            else:
                grade = "D"
        else:
            grade = "N/A"
        
        lines.append(f"  Grade: {grade}")
        
        # Counter-directional warning
        if total_sig > 0 and passed / max(total_sig, 1) < 0.3:
            lines.append("  WARNING: Counter-directional: >=70% of features moved opposite to task expectations")
        
        lines.append(f"  Passed Features (n={passed}):")
        if passed_features:
            for feat in passed_features[:15]:
                lines.append(f"    {feat}")
        else:
            lines.append("    (none)")
        
        # Top Drivers — exclude artifact-suspect features (|d|>10)
        lines.append("  Top Drivers (by |d|, artifact-suspect excluded):")
        if sig_features:
            clean_sig = [(fn, fd) for fn, fd in sig_features
                         if Enhanced64ChannelReportGenerator._feature_is_profile_safe(fn, fd)
                         and abs(fd.get('hedges_g', fd.get('effect_size_d', 0))) <= 10.0]
            top_drivers = sorted(clean_sig,
                                 key=lambda x: abs(x[1].get('hedges_g', x[1].get('effect_size_d', 0))),
                                 reverse=True)[:3]
            for feat_name, feat_data in top_drivers:
                d = abs(feat_data.get('hedges_g', feat_data.get('effect_size_d', 0)))
                lines.append(f"    {feat_name}: |d|={d:.6f}")
            if not top_drivers:
                lines.append("    (none — all significant features are artifact-suspect)")
        else:
            lines.append("    (none)")
        
        return lines
        
        # Notes
        lines.append("  Notes:")
        lines.append("    • 64-channel extended montage analysis")
        if 'gamma' in task_name.lower():
            lines.append("    • Gamma evaluation guarded by EMG flag in some windows")
        
        return lines
    
    @staticmethod
    def _generate_combined_summary(combined: Dict[str, Any]) -> List[str]:
        """Generate combined aggregate summary."""
        lines = []
        
        summary = combined.get('summary', {})
        fisher = summary.get('fisher', {})
        sum_p = summary.get('sum_p', {})
        composite_info = summary.get('composite', {})
        
        # Use correct field names from task_summary structure
        fisher_p = fisher.get('km_p', 1.0)
        fisher_sig = fisher.get('significant', False)
        fisher_df = fisher.get('km_df', 0.0)
        if isinstance(fisher_p, (int, float)) and fisher_p == 0:
            fisher_p_str = "0"
        else:
            fisher_p_str = f"{fisher_p:.6g}" if isinstance(fisher_p, (int, float)) else str(fisher_p)
        lines.append(f"Fisher_p={fisher_p_str} sig={fisher_sig} df={fisher_df:.4f} method=independence_approximation")
        
        # SumP - use correct field 'value' not 'observed_sum'
        sum_p_obs = sum_p.get('value', sum_p.get('observed_sum', 0.0))
        sum_p_pval = sum_p.get('perm_p', sum_p.get('chi2_p', 'N/A'))
        sum_p_sig = sum_p.get('significant', False)
        perm_used = sum_p.get('permutation_used', False)
        if isinstance(sum_p_pval, (int, float)):
            sum_p_pval_str = f"{sum_p_pval:.6f}" if sum_p_pval > 0.000001 else f"{sum_p_pval:.6g}"
        else:
            sum_p_pval_str = str(sum_p_pval)
        lines.append(f"SumP={sum_p_obs:.4f} p={sum_p_pval_str} sig={sum_p_sig} perm={perm_used}")
        
        # CompositeScore from composite.score, Mean|d| from effect_size_mean
        composite = composite_info.get('score', summary.get('composite_score', 0.0))
        mean_d = summary.get('effect_size_mean', 0.0)
        median_d = summary.get('effect_size_median', 0.0)
        artifact_suspect_n = summary.get('artifact_suspect_count', 0)
        winsor_note = f" [Mean|d| Winsorised: {artifact_suspect_n} features capped at |d|=10]" if artifact_suspect_n > 0 else ""
        lines.append(f"CompositeScore={composite:.3f} Mean|d|={mean_d:.6f} Median|d|={median_d:.6f}{winsor_note}")
        
        # Get alpha from fisher
        alpha = fisher.get('alpha', 0.05)
        feature_sel = summary.get('feature_selection', {})
        fdr_alpha = feature_sel.get('fdr_alpha', 0.05) if feature_sel else 0.05
        lines.append(f"Decision thresholds (band-specific): p≤{alpha}, q≤{fdr_alpha}")
        lines.append("  Effect sizes: α≥0.25, β≥0.35, γ≥0.30, θ≥0.30, ratios≥0.30")
        lines.append("  Percent change: relative features≥5%, absolute≥10%")
        
        # Correlation guard if available
        fisher_km_corr = fisher.get('km_mean_r', 0.0)
        total_features = fisher.get('k_features', 70)
        if total_features > 0:
            m_eff = total_features / max(1 + fisher_km_corr * (total_features - 1), 1)
            guard_factor = m_eff / total_features
            lines.append(f"Correlation guard factor={guard_factor:.5f} (m_eff={m_eff:.4f}/{total_features})")
        
        return lines
    
    @staticmethod
    def _generate_omnibus_summary(across_task: Dict[str, Any],
                                  suppress_gamma: bool = False) -> List[str]:
        """Generate across-task omnibus summary from across_task results."""
        lines = []
        
        # Handle the actual structure from _analyze_across_tasks
        features = across_task.get('features', {})
        fdr_alpha = across_task.get('fdr_alpha', 0.05)
        ranking_only = across_task.get('ranking_only', False)
        
        if ranking_only:
            # Ranking-only mode - insufficient sessions for significance testing
            msg = across_task.get('message', 'Insufficient sessions for significance testing')
            lines.append(f"WARNING: {msg}")
            lines.append(f"Features analyzed: {len(features)}")
            lines.append("")
            return lines
        
        lines.append("Profile-facing omnibus lists exclude artifact-suspect and EMG-excluded gamma features.")

        # Count significant features
        sig_feats = [
            f for f, data in features.items()
            if data.get('omnibus_sig', False)
            and Enhanced64ChannelReportGenerator._feature_is_profile_safe(
                f, data, suppress_gamma=suppress_gamma)
        ]
        total_tested = len(features)
        
        lines.append(f"Features tested: {total_tested} | Significant (FDR {fdr_alpha}): {len(sig_feats)}")

        # Saturation warning
        if total_tested > 0:
            sat_ratio = len(sig_feats) / total_tested
            if sat_ratio > 0.85:
                lines.append(
                    f"  [!] SATURATION WARNING: {len(sig_feats)}/{total_tested} ({sat_ratio*100:.0f}%) "
                    f"features significant across tasks. Above 85% critical threshold — pipeline "
                    f"response is non-specific. Omnibus results should not be used for profiling."
                )
        
        if sig_feats:
            # Show comma-separated list like in sample
            feat_list = ", ".join(sorted(sig_feats))
            lines.append(f"Significant features: {feat_list}")
            lines.append("")

            q_mismatch = any(
                isinstance(features[k].get('omnibus_p', None), (int, float))
                and isinstance(features[k].get('omnibus_q', None), (int, float))
                and features[k].get('omnibus_q', 1.0) + 1e-15 < features[k].get('omnibus_p', 0.0)
                for k in sig_feats
            )
            if q_mismatch:
                lines.append(
                    "Top Feature Omnibus Stats suppressed: omnibus q-values are smaller than "
                    "their raw p-values for this feature family, indicating p/q misalignment "
                    "or non-standard q semantics. Treat omnibus output as QC-only until fixed.")
                return lines
            
            # Top feature stats by omnibus statistic
            lines.append("Top Feature Omnibus Stats (up to 5):")
            sorted_feats = sorted(
                [(k, features[k]) for k in sig_feats],
                key=lambda x: x[1].get('statistic', 0),
                reverse=True
            )
            for feat_name, feat_data in sorted_feats[:5]:
                stat = feat_data.get('statistic', 0)
                p = feat_data.get('omnibus_p', 1)
                q = feat_data.get('omnibus_q', 1)
                lines.append(f"  {feat_name}: stat={stat:.2f} p={p:.6g} q={q:.6g}")
        else:
            lines.append("No features showed significant variation across tasks.")
        
        return lines
    
    @staticmethod
    def _generate_multichannel_summary(results: Dict[str, Any], analysis_results: Optional[Dict] = None,
                                       suitability: Optional[str] = None) -> List[str]:
        """Generate 64-channel specific analysis: regional, asymmetry, and coherence."""
        lines = []
        analysis_results = analysis_results or {}
        
        # Detect whether gamma EMG flood exclusion is active
        gamma_emg_excluded = any(
            v.get('emg_excluded', False)
            for v in analysis_results.values()
            if isinstance(v, dict)
        )
        
        # ===== REGIONAL ACTIVITY ANALYSIS =====
        lines.append("")
        lines.append("Regional Activity Summary")
        lines.append("-"*40)
        lines.append("Analysis of brain activity by anatomical region across all tasks.")
        lines.append("Artifact-suspect features and EMG-excluded gamma features are excluded from interpretive summaries.")
        lines.append("")
        
        # Define channel groupings by region (10-20 extended system)
        regions = {
            'Frontal': ['Fp1', 'Fp2', 'AF3', 'AF4', 'AF7', 'AF8', 'F1', 'F2', 'F3', 'F4', 
                       'F5', 'F6', 'F7', 'F8', 'Fz', 'FC1', 'FC2', 'FC3', 'FC4', 'FC5', 'FC6'],
            'Central': ['C1', 'C2', 'C3', 'C4', 'C5', 'C6', 'Cz', 'CP1', 'CP2', 
                       'CP3', 'CP4', 'CP5', 'CP6'],
            'Parietal': ['P1', 'P2', 'P3', 'P4', 'P5', 'P6', 'P7', 'P8', 'Pz', 
                        'PO3', 'PO4', 'PO7', 'PO8'],
            'Temporal': ['T7', 'T8', 'FT7', 'FT8', 'TP7', 'TP8'],
            'Occipital': ['O1', 'O2', 'Oz', 'PO3', 'PO4']
        }
        
        bands = ['delta', 'theta', 'alpha', 'beta', 'gamma']
        
        # Extract regional features from analysis_results
        regional_stats = {}
        for region_name, channels in regions.items():
            regional_stats[region_name] = {band: {'count': 0, 'sig_increase': 0, 'sig_decrease': 0, 
                                                   'avg_effect': 0.0, 'max_effect': 0.0} 
                                          for band in bands}
        
        # Analyze features for regional patterns
        for feat_name, feat_data in analysis_results.items():
            if not Enhanced64ChannelReportGenerator._feature_is_profile_safe(feat_name, feat_data):
                continue
            # Parse feature name to extract channel and band
            for region_name, channels in regions.items():
                for channel in channels:
                    if channel.lower() in feat_name.lower():
                        for band in bands:
                            if band in feat_name.lower():
                                # Engine writes 'hedges_g'/'significant';
                                # 'effect_size_d'/'significant_change' kept as legacy fallback.
                                d = feat_data.get('hedges_g',
                                                  feat_data.get('effect_size_d', 0.0))
                                is_sig = feat_data.get('significant',
                                                       feat_data.get('significant_change', False))
                                
                                regional_stats[region_name][band]['count'] += 1
                                regional_stats[region_name][band]['avg_effect'] += abs(d)
                                regional_stats[region_name][band]['max_effect'] = max(
                                    regional_stats[region_name][band]['max_effect'], abs(d))
                                
                                if is_sig:
                                    if d > 0:
                                        regional_stats[region_name][band]['sig_increase'] += 1
                                    else:
                                        regional_stats[region_name][band]['sig_decrease'] += 1
        
        # Pre-extract channel quality for occipital warning (also used later in coverage section)
        _artifact_summary_early = results.get('artifact_summary', {})
        _channel_quality_early = _artifact_summary_early.get('channel_quality', {})

        # Report regional findings
        for region_name in ['Frontal', 'Central', 'Parietal', 'Temporal', 'Occipital']:
            lines.append(f"{region_name} Region:")
            region_data = regional_stats[region_name]

            # Occipital coverage warning — suppress visual inferences when data are sparse
            if region_name == 'Occipital' and _channel_quality_early:
                occ_chs = regions['Occipital']
                occ_good = sum(1 for ch in occ_chs
                               if ch in _channel_quality_early and _channel_quality_early[ch] >= 0.7)
                if occ_good < 2:
                    lines.append(
                        f"  [!] LOW COVERAGE: {occ_good}/{len(occ_chs)} good occipital channels"
                        f" — visual/occipital inferences suppressed.")

            for band in bands:
                band_data = region_data[band]
                if band_data['count'] > 0:
                    avg_eff = band_data['avg_effect'] / band_data['count']
                    sig_total = band_data['sig_increase'] + band_data['sig_decrease']
                    
                    if sig_total > 0:
                        direction = "↑" if band_data['sig_increase'] > band_data['sig_decrease'] else "↓"
                        emg_tag = " [EMG-excluded]" if (band == 'gamma' and gamma_emg_excluded) else ""
                        lines.append(f"  {band.capitalize():8s}: {sig_total:2d} sig features {direction} "
                                   f"(avg |d|={avg_eff:.3f}, max |d|={band_data['max_effect']:.3f}){emg_tag}")
            
            lines.append("")
        
        # ===== HEMISPHERIC ASYMMETRY ANALYSIS =====
        lines.append("Hemispheric Asymmetry Analysis")
        lines.append("-"*40)
        lines.append("Comparison of left vs right hemisphere activity patterns.")
        lines.append("Artifact-suspect features and EMG-excluded gamma features are excluded.")
        lines.append("")
        
        # Define hemispheric channels
        left_channels = ['Fp1', 'AF3', 'AF7', 'F1', 'F3', 'F5', 'F7', 'FC1', 'FC3', 'FC5',
                        'C1', 'C3', 'C5', 'T7', 'FT7', 'TP7', 'CP1', 'CP3', 'CP5',
                        'P1', 'P3', 'P5', 'P7', 'PO3', 'PO7', 'O1']
        right_channels = ['Fp2', 'AF4', 'AF8', 'F2', 'F4', 'F6', 'F8', 'FC2', 'FC4', 'FC6',
                         'C2', 'C4', 'C6', 'T8', 'FT8', 'TP8', 'CP2', 'CP4', 'CP6',
                         'P2', 'P4', 'P6', 'P8', 'PO4', 'PO8', 'O2']
        
        # Calculate asymmetry metrics by band
        asymmetry_stats = {band: {'left_sig': 0, 'right_sig': 0, 'left_avg_d': 0.0, 
                                  'right_avg_d': 0.0, 'count_left': 0, 'count_right': 0}
                          for band in bands}
        
        for feat_name, feat_data in analysis_results.items():
            if not Enhanced64ChannelReportGenerator._feature_is_profile_safe(feat_name, feat_data):
                continue
            is_sig = feat_data.get('significant',
                                   feat_data.get('significant_change', False))
            d = feat_data.get('hedges_g',
                              feat_data.get('effect_size_d', 0.0))
            
            # Check hemisphere
            is_left = any(ch.lower() in feat_name.lower() for ch in left_channels)
            is_right = any(ch.lower() in feat_name.lower() for ch in right_channels)
            
            for band in bands:
                if band in feat_name.lower():
                    if is_left:
                        asymmetry_stats[band]['count_left'] += 1
                        asymmetry_stats[band]['left_avg_d'] += abs(d)
                        if is_sig:
                            asymmetry_stats[band]['left_sig'] += 1
                    elif is_right:
                        asymmetry_stats[band]['count_right'] += 1
                        asymmetry_stats[band]['right_avg_d'] += abs(d)
                        if is_sig:
                            asymmetry_stats[band]['right_sig'] += 1
        
        # Report asymmetry findings
        for band in bands:
            band_data = asymmetry_stats[band]
            left_count = band_data['count_left']
            right_count = band_data['count_right']
            
            if left_count > 0 and right_count > 0:
                left_avg = band_data['left_avg_d'] / left_count
                right_avg = band_data['right_avg_d'] / right_count
                
                asymmetry_index = (left_avg - right_avg) / (left_avg + right_avg) if (left_avg + right_avg) > 0 else 0
                
                dominant = "Left" if asymmetry_index > 0.1 else ("Right" if asymmetry_index < -0.1 else "Balanced")
                
                emg_tag = " [EMG-excluded]" if (band == 'gamma' and gamma_emg_excluded) else ""
                lines.append(f"{band.capitalize():8s}: Left sig={band_data['left_sig']:2d} (avg |d|={left_avg:.3f}) | "
                           f"Right sig={band_data['right_sig']:2d} (avg |d|={right_avg:.3f}) | "
                           f"Asymmetry={asymmetry_index:+.3f} ({dominant}){emg_tag}")
        
        lines.append("")
        
        # ===== COHERENCE & CONNECTIVITY ANALYSIS =====
        lines.append("Inter-Channel Coherence & Connectivity")
        lines.append("-"*40)
        lines.append("Analysis of functional connectivity between brain regions.")
        lines.append("Artifact-suspect connectivity features and EMG-excluded gamma features are excluded.")
        lines.append("")
        
        # Look for coherence features in analysis_results
        # Match: 'coherence', 'connectivity', 'coh_*', 'dwpli_*', 'wpli_*'
        coherence_features = {}
        for feat_name, feat_data in analysis_results.items():
            if not Enhanced64ChannelReportGenerator._feature_is_profile_safe(feat_name, feat_data):
                continue
            feat_lower = feat_name.lower()
            is_connectivity = (
                'coherence' in feat_lower or 
                'connectivity' in feat_lower or
                feat_lower.startswith('coh_') or
                feat_lower.startswith('dwpli_') or
                feat_lower.startswith('wpli_')
            )
            if is_connectivity:
                is_sig = feat_data.get('significant',
                                       feat_data.get('significant_change', False))
                d = feat_data.get('hedges_g',
                                  feat_data.get('effect_size_d', 0.0))
                p = feat_data.get('p_value', 1.0)
                
                if is_sig:
                    coherence_features[feat_name] = {
                        'd': d,
                        'p': p,
                        'direction': 'increased' if d > 0 else 'decreased'
                    }
        
        if coherence_features:
            lines.append(f"Significant Coherence Changes: {len(coherence_features)} features")
            
            # Sort by effect size
            sorted_coh = sorted(coherence_features.items(), 
                              key=lambda x: abs(x[1]['d']), reverse=True)
            
            lines.append("Top Connectivity Changes:")
            for feat_name, feat_data in sorted_coh[:10]:
                lines.append(f"  {feat_name}: {feat_data['direction']} "
                           f"(d={feat_data['d']:+.3f}, p={feat_data['p']:.6g})")
            
            # Count increases vs decreases
            increases = sum(1 for f in coherence_features.values() if f['d'] > 0)
            decreases = len(coherence_features) - increases
            
            lines.append("")
            lines.append(f"Net Connectivity: {increases} increased, {decreases} decreased")
            
            if suitability and suitability != "PROFILE-READY":
                lines.append(
                    f"  Interpretation disabled: session is {suitability}; connectivity distribution "
                    "is shown for QC review only.")
            elif increases > decreases * 2:
                lines.append("  → Overall pattern suggests enhanced functional integration")
            elif decreases > increases * 2:
                lines.append("  → Overall pattern suggests reduced functional integration")
            else:
                lines.append("  → Mixed pattern with both integration and segregation")
        else:
            lines.append("No significant coherence features detected.")
            lines.append("Note: Coherence analysis requires features named with 'coherence' or 'connectivity'")
        
        lines.append("")
        
        # ===== CHANNEL QUALITY & COVERAGE =====
        lines.append("Channel Quality & Spatial Coverage")
        lines.append("-"*40)
        
        # Extract artifact information
        artifact_summary = results.get('artifact_summary', {})
        bad_channels = artifact_summary.get('bad_channels', [])
        channel_quality = artifact_summary.get('channel_quality', {})
        
        good_channels = [ch for ch, qual in channel_quality.items() if qual >= 0.7]
        fair_channels = [ch for ch, qual in channel_quality.items() if 0.4 <= qual < 0.7]
        poor_channels = [ch for ch, qual in channel_quality.items() if qual < 0.4]
        
        lines.append(f"Total Channels: 64")
        lines.append(f"  Good Quality (≥70%): {len(good_channels)} channels")
        lines.append(f"  Fair Quality (40-69%): {len(fair_channels)} channels")
        lines.append(f"  Poor Quality (<40%): {len(poor_channels)} channels")
        
        if bad_channels:
            bad_ch_str = ', '.join(str(ch) for ch in bad_channels)
            lines.append(f"  Channels globally excluded from feature extraction: {bad_ch_str}")
        lines.append(
            "  Note: quality bins are mean per-channel quality across phases; global exclusion "
            "uses flat-channel or majority-noisy rules, so excluded-channel counts need not "
            "match the poor-quality bin.")
        
        # Regional coverage
        lines.append("")
        lines.append("Spatial Coverage by Region:")
        for region_name, channels in regions.items():
            good_in_region = sum(1 for ch in channels if ch in good_channels)
            total_in_region = len(channels)
            coverage_pct = (good_in_region / total_in_region * 100) if total_in_region > 0 else 0
            status = "[OK]" if coverage_pct >= 70 else "[!]" if coverage_pct >= 50 else "[X]"
            lines.append(f"  {region_name:10s}: {good_in_region:2d}/{total_in_region:2d} good channels "
                       f"({coverage_pct:.0f}%) {status}")
        
        lines.append("")
        lines.append("  Note: [OK] ≥70%; [!] 50–69%; [X] <50% (interpret with caution)")
        lines.append("")
        
        # ===== TOPOGRAPHIC PATTERNS =====
        lines.append("Topographic Distribution Summary")
        lines.append("-"*40)
        lines.append("Spatial patterns of significant changes across the scalp.")
        lines.append("Artifact-suspect features and EMG-excluded gamma features are excluded.")
        lines.append("")
        
        # Count significant features by anterior-posterior axis
        anterior_sig = 0  # Frontal + Temporal
        central_sig = 0   # Central
        posterior_sig = 0  # Parietal + Occipital
        
        for feat_name, feat_data in analysis_results.items():
            if feat_data.get('significant',
                             feat_data.get('significant_change', False)):
                if not Enhanced64ChannelReportGenerator._feature_is_profile_safe(feat_name, feat_data):
                    continue
                if any(ch.lower() in feat_name.lower() 
                      for ch in regions['Frontal'] + regions['Temporal']):
                    anterior_sig += 1
                elif any(ch.lower() in feat_name.lower() 
                        for ch in regions['Central']):
                    central_sig += 1
                elif any(ch.lower() in feat_name.lower() 
                        for ch in regions['Parietal'] + regions['Occipital']):
                    posterior_sig += 1
        
        total_spatial = anterior_sig + central_sig + posterior_sig
        if total_spatial > 0:
            ant_pct = anterior_sig / total_spatial * 100
            cen_pct = central_sig / total_spatial * 100
            post_pct = posterior_sig / total_spatial * 100
            
            lines.append(f"Anterior (Frontal/Temporal): {anterior_sig} features ({ant_pct:.1f}%)")
            lines.append(f"Central (Sensorimotor):      {central_sig} features ({cen_pct:.1f}%)")
            lines.append(f"Posterior (Parietal/Occip):  {posterior_sig} features ({post_pct:.1f}%)")
            lines.append("")
            
            # Determine dominant pattern
            if ant_pct > 50:
                pattern = "Anterior-dominant (frontal/temporal focus)"
                context = "Common in attention, executive, and language tasks"
            elif post_pct > 50:
                pattern = "Posterior-dominant (parietal/occipital focus)"
                context = "Common in visual, spatial, and memory tasks"
            elif cen_pct > 40:
                pattern = "Central-dominant (sensorimotor focus)"
                context = "Common in motor imagery and tactile tasks"
            else:
                pattern = "Distributed (whole-brain involvement)"
                context = "Suggests complex task with multiple cognitive components"
            
            if suitability and suitability != "PROFILE-READY":
                context = (
                    f"Interpretation disabled: session is {suitability}; "
                    "distribution is shown for QC review only.")
            lines.append(f"Topographic Pattern: {pattern}")
            lines.append(f"  → {context}")
        else:
            lines.append("No significant spatial features detected.")
        
        lines.append("")

        return lines
