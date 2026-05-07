# Offline 64-Channel EEG Pipeline - Professor Meeting Explainer

**Purpose:** Help explain the current analyzer clearly in a meeting.  
**Use this with:** `analysis_report_fast_20260427_165750.txt` and `docs/Offline_64Channel_Analysis_Pipeline.md`.

---

## 1. One-Minute Summary

The offline analyzer records raw 64-channel EEG first, then processes it after the session. The current pipeline extracts spectral, regional, asymmetry, connectivity, and global features, compares each task against baseline, and then applies several safety gates before allowing profile-style interpretation.

The most important point for the professor:

> The pipeline is now designed to prevent contaminated EEG from becoming a cognitive profile. In the latest report, the safeguards worked: the session was marked `RESEARCH-ONLY` because gamma EMG flood, extreme artifact-suspect features, and high-frequency saturation were all present.

So the current report is not profile-compatible, but that is scientifically appropriate. It is a QC/research report showing the recording is too contaminated for profiling.

---

## 2. What Problem We Are Solving

The application goal is profiling from EEG tasks. That requires more than finding significant features. It requires:

- Clean enough data.
- A suitable baseline.
- Artifact-resistant features.
- Task signatures that can be separated reliably.
- Report sections that do not accidentally imply cognitive meaning from artifacts.

The original issue was that contaminated gamma and extreme feature values could still appear in top-feature lists and spatial summaries. That made the report unsafe for profiling because a downstream model or reader could treat artifact as brain signal.

The updated pipeline now structurally blocks that.

---

## 3. How The Pipeline Works

### Step 1: Record raw EEG and markers

During the session, the system records:

- 64 EEG channels at 500 Hz.
- Phase markers: eyes-closed baseline, eyes-open baseline, task phases.
- Task labels such as attention, math, imagery, emotion.

The important design choice is that the real-time system does not do heavy analysis while streaming. It preserves the raw data for offline analysis.

### Step 2: Segment by phase

The analyzer cuts the recording into:

- Baseline windows.
- Task windows.
- Optional protocol/data-collection phases.

In the current report:

```text
Tasks executed: 5
Tasks analyzed statistically: 4
```

This means one phase was recorded but excluded from statistical comparison, likely a protocol/data-collection task such as 40 Hz stimulation.

### Step 3: Preprocess and reject obvious artifacts

The pipeline checks:

- Bad channels.
- Flat channels.
- Very noisy channels.
- Line noise.
- High-frequency muscle-like windows.

A key update is the high-frequency artifact gate before feature extraction. It looks for broadband 30-45 Hz power spikes globally and in frontal/temporal channels.

### Step 4: Avoid over-pruning with the saturation guard

If the high-frequency gate would reject too many windows, it does not keep only a tiny remaining sample. That would bias the task comparison.

Instead, it marks the phase as tonically contaminated:

```text
High-frequency saturation guard activated in 20 phase(s):
574 candidate windows left in place to avoid biased tiny-sample analysis
```

How to explain this:

> The data were not just contaminated by a few bad windows. The high-frequency contamination was so widespread that normal rejection would have removed most of the session. So the pipeline correctly refused to pretend it had a clean sample.

### Step 5: Extract features

Features include:

- Delta, theta, alpha, beta, gamma power.
- Relative band power.
- Peak frequencies.
- Alpha/theta and beta/alpha ratios.
- Regional features.
- Hemispheric asymmetry.
- Coherence/connectivity.
- Global field power.

### Step 6: Compare task vs baseline

Current statistical behavior:

- Uses eyes-closed baseline as the main reference.
- Aggregates windows into blocks to reduce autocorrelation.
- Uses Mann-Whitney U for per-feature task-vs-baseline comparisons.
- Corrects feature p-values with Benjamini-Hochberg FDR.
- Reports Hedges' g effect sizes.
- Uses Fisher combined p-value as an independence approximation, not as a full correlated-feature correction.

### Step 7: Apply profile-safety gates

The report decides whether the result is:

- `PROFILE-READY`
- `RESEARCH-ONLY`
- `INVALID`

The current report is:

```text
PROFILE SUITABILITY: RESEARCH-ONLY
```

---

## 4. Why The Current Report Is Not Profile-Compatible

The current report has three major blocking issues.

### 4.1 Gamma EMG flood

Gamma is 30-45 Hz. Scalp EEG gamma overlaps strongly with muscle activity from jaw, face, neck, and scalp.

The report shows gamma flood in all four analyzed tasks:

```text
visual_imagery 65%
attention_focus 50%
mental_math 51%
emotion_face 88%
```

This means too many gamma features were significant at once. Real cortical gamma should usually be more spatially specific. Broad gamma significance across the scalp is more consistent with EMG contamination.

Current safeguard:

- Gamma is excluded from omnibus statistics.
- Gamma is removed from top-feature lists.
- Gamma appears only in an `EMG-excluded gamma diagnostics` section.

How to say it:

> We are not claiming gamma brain activation from this session. The pipeline explicitly treats gamma as contaminated and excludes it from profile-facing sections.

### 4.2 Artifact-suspect features

The report shows:

```text
243 unique feature names / 332 task-feature instances with |d| > 10
```

Effect sizes this large are not plausible as normal EEG task effects. They are more likely movement, electrode instability, or contaminated channels.

Current safeguard:

- These features are excluded from profile-facing top lists.
- They are excluded from spatial/connectivity summaries.
- They are still shown separately for audit/QC.

How to say it:

> We preserve these values for transparency, but we do not let them drive interpretation.

### 4.3 HF saturation

The high-frequency artifact gate found widespread contamination:

```text
20 phase(s) tonically contaminated
574 candidate windows left in place
```

This is a strong reason not to profile. It means the recording problem is broad, not isolated.

How to say it:

> The rejection gate did not fail; it detected that rejection would over-prune the data. That is why the report is research-only.

---

## 5. What The Updated Report Does Correctly

These are good points to mention.

### Gamma does not leak into top feature lists

Before the latest update, gamma could still appear in "Top 5 Features" even though the report said gamma was excluded. That was confusing and unsafe.

Now:

- Top lists say `artifact-suspect/EMG-excluded excluded`.
- Gamma only appears in `EMG-excluded gamma diagnostics`.

### Spatial/connectivity summaries are filtered

Before, extreme connectivity values such as `d=-40` could appear in interpretive sections.

Now:

- Artifact-suspect features are excluded.
- EMG-excluded gamma features are excluded.
- Research-only sessions disable interpretation text.

### Cross-task FWER is clearer

The report now says:

```text
No task-level omnibus effects survived Holm-Bonferroni family-wise correction.
No reliable between-task differentiation was detected.
```

This matters because if task signatures are not reliably separable, profiling should not proceed.

### Suspicious omnibus rankings are suppressed

The report suppresses the "Top Feature Omnibus Stats" if adjusted q-values are smaller than raw p-values, which is mathematically suspicious under ordinary FDR reporting.

How to say it:

> We would rather suppress an unstable ranking than show something that could be misused downstream.

---

## 6. Baseline Limitation To Be Honest About

Current baseline:

```text
Baseline: eyes-closed only
```

This is acceptable for some research comparisons, but it is a limitation for profile-ready cognitive tasks.

Why:

- Eyes-closed and eyes-open states differ strongly.
- Alpha changes can reflect eye state rather than task cognition.
- Visual and cognitive tasks are normally eyes-open.

Better future policy:

- Resting profile: compare to eyes-closed.
- Eyes-open tasks: compare to eyes-open.
- Best option: task-specific pre-task baseline.

How to say it:

> For this contaminated session the baseline issue is secondary, because the profile gate already blocks interpretation. But for future clean sessions, baseline design becomes critical.

---

## 7. What You Can Safely Claim

Safe claims:

- The pipeline records raw 64-channel EEG and analyzes it offline.
- It now includes artifact-aware profile-safety gates.
- The current session is research-only, not profile-ready.
- Gamma contamination was detected and structurally excluded from profile-facing outputs.
- Extreme effect-size features are treated as artifact-suspect and excluded from interpretation.
- The high-frequency gate detected tonic contamination and prevented biased tiny-sample analysis.
- The current report can be used to discuss QC and pipeline behavior.

Do not claim:

- The subject has a cognitive profile from this session.
- The subject has attention, emotional, or math traits from this session.
- Gamma results reflect cortical gamma.
- Connectivity changes reflect real network changes in this session.
- The current system is validated for diagnostic inference.

---

## 8. Suggested Meeting Script

You can say:

> I wanted to make the pipeline scientifically conservative before using it for profiling. The current report is not profile-ready, but that is actually the correct outcome. The data show gamma EMG flood across all analyzed tasks, many artifact-suspect features with very large effect sizes, and high-frequency saturation across phases. The updated report now blocks profiling and moves contaminated gamma into a diagnostic-only section.

Then:

> The main design principle is that profile-facing sections only show features that pass artifact guards. Artifact-suspect features and EMG-excluded gamma are still retained for audit, but they cannot drive top-feature lists, spatial interpretation, or connectivity interpretation.

Then:

> The remaining scientific questions are baseline design, advanced EMG cleaning, and validation. For profile-ready use, I think we need cleaner acquisition, eyes-open or task-specific baselines for eyes-open tasks, and validation of ICA/CSD/CCA or another artifact-removal approach.

---

## 9. Questions To Ask The Professor

Ask these to get useful guidance.

1. **Baseline design**

   Should eyes-open cognitive tasks be compared to eyes-open baseline, task-specific pre-task baseline, or both?

2. **Gamma handling**

   Should gamma be excluded entirely from profile-facing reports unless ICA/CSD/CCA cleaning and validation are available?

3. **Artifact thresholds**

   Is `|d| > 10` a reasonable artifact-suspect cutoff for this exploratory pipeline, or should we use a stricter threshold?

4. **HF saturation**

   When high-frequency saturation is present, should the whole session be blocked from profiling automatically?

5. **Validation**

   What validation standard would be acceptable before calling a report "profile-ready"? Test-retest reliability? Known task effects? Comparison against an external EEG package?

6. **Statistical approach**

   Is Mann-Whitney U plus FDR appropriate for the current feature-level analysis, or should we move toward mixed models/permutation testing for publication?

7. **Connectivity**

   Should coherence/connectivity be profile-facing at all, or kept as exploratory until more robust preprocessing is implemented?

---

## 10. Likely Professor Critiques And Good Answers

### "Why are there so many significant results?"

Answer:

> That is exactly why the report is research-only. The gamma flood and artifact-suspect counts suggest non-specific contamination rather than meaningful task signatures.

### "Why not just remove the contaminated windows?"

Answer:

> The HF gate tried. The saturation guard found contamination in so many windows that dropping them would leave a biased tiny sample. So the pipeline reports tonic contamination instead of pretending the remaining sample is clean.

### "Why use eyes-closed baseline for eyes-open tasks?"

Answer:

> That is a current limitation. The report now states it explicitly. For profile-ready use, we should compare eyes-open tasks to eyes-open or task-specific pre-task baseline.

### "Can you interpret the spatial pattern?"

Answer:

> Not for profiling in this session. The report shows the distribution for QC only, and interpretation is disabled because the session is research-only.

### "Is this scientifically valid?"

Answer:

> The current pipeline is valid as a conservative QC and exploratory analysis pipeline. It is not yet validated as a profiling instrument. The safeguards are designed to prevent overclaiming.

---

## 11. Development Roadmap To Propose

Short-term:

- Recollect a cleaner session with better cap fit and explicit jaw/face relaxation instructions.
- Add an eyes-open baseline policy for eyes-open tasks.
- Keep gamma excluded from profile-facing reports when flood is active.
- Keep connectivity exploratory.

Medium-term:

- Implement and validate ICA + CSD/Laplacian path.
- Evaluate CCA-based muscle artifact removal.
- Add independent verification against MNE/Python or another established EEG package.
- Run repeated sessions to measure reliability.

Long-term:

- Define profile-ready criteria prospectively.
- Build normative or repeated-measures baselines.
- Validate task signatures against known EEG paradigms.
- Only then consider profile scores.

---

## 12. Bottom Line

The latest report should be presented as evidence that the pipeline is becoming safer, not as a failed profile.

The key message:

> The pipeline detected that the session was contaminated and blocked profiling. That is the scientifically responsible behavior. The next step is cleaner data collection, improved baseline design, and validated artifact-removal methods before using the output for subject profiling.

---

## 13. Feature Count And Significance Decision Process

This is the section to use if the professor asks: "How many features are extracted, and how do they become significant?"

### 13.1 How many features are extracted per window?

For a fully valid 64-channel window, the current extractor can produce about **1,396 features per 2-second window**.

Approximate breakdown:

| Feature family | Count if all channels are valid | What it measures |
|---|---:|---|
| Per-channel spectral features | 1,152 | 64 channels x 18 features each |
| Regional spectral features | 65 | 5 anatomical regions x 13 features |
| Hemispheric asymmetry | 135 | 27 left/right pairs x 5 bands |
| Frontal alpha asymmetry | 1 | `ln(F4 alpha) - ln(F3 alpha)` |
| Inter-regional coherence | 25 | 5 region pairs x 5 bands |
| Global field power | 3 | Mean, SD, and max scalp voltage dispersion |
| Global summary features | 15 | Global band powers, ratios, quality counts |
| **Theoretical total** | **1,396** | Per clean 2-second window |

Per-channel spectral features are:

- 5 absolute band powers: delta, theta, alpha, beta, gamma.
- 5 relative band powers.
- 5 peak frequencies.
- 2 ratios: alpha/theta and beta/alpha.
- 1 total neural-band power.

Important caveat:

> The theoretical maximum is not always the number tested. If channels are excluded, if a feature cannot be computed, or if gamma is excluded after EMG flood detection, the analyzed feature count is lower.

In the current report, the per-task Fisher `k` values are around **686-698** because the report is operating on the eligible, finite, non-excluded features after quality and gamma guards.

### 13.2 What is one row of features?

One feature row corresponds to one analysis window.

Current windowing:

- Window length: 2 seconds.
- Step size: 1 second.
- Overlap: 50%.

For each 2-second window, the extractor computes the feature dictionary. Then nearby overlapping windows are aggregated into larger blocks before statistical testing.

### 13.3 Why block aggregation is used

Adjacent 2-second windows overlap by 50%, so they are not independent. Treating every window as independent would inflate the sample size and make p-values too optimistic.

The pipeline therefore aggregates windows into block means:

```text
2-second overlapping windows -> 4-second block means
```

The report shows this as effective sample size:

```text
ESS: baseline=7, task=12, n_blocks=12
```

How to explain it:

> We reduce temporal autocorrelation by testing block-level feature values, not every overlapping window as if it were independent.

### 13.4 How the baseline is used

Current implementation:

- Eyes-closed windows are used as the statistical baseline.
- Eyes-open windows are retained for reference but not pooled.
- For each feature, the pipeline collects baseline block values and task block values.

A feature is only tested if:

- It exists in both baseline and task.
- It has finite numeric values in both conditions.
- Each condition has at least 3 values.
- Baseline variance is not essentially zero.

Important point:

> Missing features are not filled with zero. If a channel or feature is unavailable, that feature is skipped rather than converted into artificial data.

### 13.5 Mann-Whitney U decision step

For each eligible feature, the pipeline compares task values against baseline values with a two-sided **Mann-Whitney U test**.

Why Mann-Whitney U:

- It is non-parametric.
- It does not assume normal feature distributions.
- It is more conservative than assuming Gaussian EEG feature values.
- It compares whether task values tend to be shifted relative to baseline values.

For each feature, the pipeline stores:

- Raw p-value from Mann-Whitney U.
- Baseline mean.
- Task mean.
- Delta: task mean minus baseline mean.
- Hedges' g effect size.
- Bootstrap confidence interval for Hedges' g.

The initial candidate significance rule is:

```text
raw p < 0.05
and
absolute Hedges' g > 0.2
```

So a feature must have both statistical evidence and a minimum effect size.

### 13.6 FDR correction decision step

Because hundreds of features are tested, raw p-values alone are not enough. Testing many features creates false positives.

The pipeline applies **Benjamini-Hochberg false discovery rate correction** across the tested feature family.

For each feature:

```text
raw p-value -> FDR-adjusted q-value
```

The FDR decision is:

```text
q <= 0.05
```

How to explain it:

> Mann-Whitney U gives the raw per-feature p-value. FDR correction asks whether that feature still looks reliable after accounting for the fact that we tested many features.

### 13.7 Effect size decision step

The pipeline reports **Hedges' g** for each feature.

Interpretation:

- `d` or `g` near 0: small/no effect.
- Larger absolute values: stronger baseline-to-task shift.
- Direction indicates increase or decrease.

But very large values are not trusted.

Artifact-suspect rule:

```text
|d| > 10 -> artifact_suspect
```

Those features are:

- Preserved for audit.
- Excluded from profile-facing top lists.
- Excluded from spatial/connectivity interpretation.
- Counted as a profile-blocking reason.

How to explain it:

> A very small p-value with an absurd effect size is not automatically meaningful. In EEG, it often means artifact. That is why we combine p-values, FDR, effect size, and artifact guards.

### 13.8 Gamma decision step

After feature-level testing, the pipeline counts how many gamma features were significant.

Gamma flood rule:

```text
significant gamma features / total gamma features > 25%
```

If true:

- Gamma is marked EMG-excluded.
- Gamma is removed from profile-facing top lists.
- Gamma is removed from Fisher, SumP, CompositeScore, Mean|d| summaries.
- Gamma remains only as diagnostic evidence.

How to explain it:

> We are not asking whether one gamma electrode changed. We are asking whether gamma significance floods the scalp. A widespread gamma flood is more consistent with muscle artifact than cortical gamma.

### 13.9 Omnibus and aggregate decisions

After per-feature decisions, the pipeline computes aggregate summaries.

| Metric | What it means | Caution |
|---|---|---|
| Fisher p | Combines feature p-values | Reported as independence approximation; EEG features are correlated |
| SumP | Sum of raw p-values | Sensitive to broad weak effects |
| CompositeScore | Sum of `-log10(q)` for FDR-significant features | Not a cognitive score |
| Mean/Median \|d\| | Average effect size among significant features | Mean is Winsorized when artifact-suspect features exist |
| Cross-task FWER | Holm-Bonferroni task-level correction | If no task survives, do not infer task-specific profiles |

In the current report:

```text
No task-level omnibus effects survived Holm-Bonferroni family-wise correction.
No reliable between-task differentiation was detected.
```

That is another reason the report should not be used for task-specific profiling.

### 13.10 Final decision chain

A simplified decision chain is:

```text
Extract feature per 2 s window
        |
Aggregate into block-level values
        |
Require finite baseline and task values
        |
Mann-Whitney U raw p-value
        |
Hedges' g effect size
        |
Benjamini-Hochberg FDR q-value
        |
Artifact-suspect guard: remove |d| > 10 from profile-facing interpretation
        |
Gamma flood guard: remove EMG-excluded gamma from profile-facing interpretation
        |
Cross-task/profile suitability gates Holm-Bonferroni family-wise correction
        |
PROFILE-READY, RESEARCH-ONLY, or INVALID
```

Short answer for the professor:

> Each clean 2-second window can produce about 1,396 features. A feature becomes a candidate task effect only if task and baseline have enough finite block-level values, Mann-Whitney U gives p < 0.05, the effect size is meaningful, and the FDR-adjusted q-value supports it. Even then, profile-facing interpretation is blocked if the feature is artifact-suspect, gamma is EMG-excluded, or the session-level profile gate fails.
