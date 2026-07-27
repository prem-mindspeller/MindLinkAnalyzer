# MindRove live signal quality

## Current behaviour

The live plot and recordings use their existing 1-45 Hz band-pass and 50 Hz notch-filtered EEG data.

1. Every second, the previous raw-signal variation check evaluates headset contact. It must see three consecutive active one-second windows before reporting Good; one inactive window reports Not Worn (`poorSignal: 200`).
2. Independently, the one-to-45 Hz band-pass and 50 Hz notch-filtered aggregate is assessed in complete five-second blocks.
3. The existing signal-quality algorithm determines whether a filtered block is noisy. Two consecutive failed blocks are required before reporting Noisy (`poorSignal: 80`); one clean block returns Good.
4. The header, live EEG page, calibration page, task selection, and task-recording gate all consume this same `poorSignal` status.

## Why this fixes the five-minute failure

The former filter-quality window was checked every second and each failure changed the UI immediately. Adjacent checks reused nearly all the same samples, so one brief disturbance could create repeated noisy reports. The recording gate also rejected more than four noisy events regardless of task duration.

The current check evaluates non-overlapping five-second filtered blocks, requires two failed blocks for Noisy, and the task gate uses a 15% noisy-time limit instead of a four-event cap. The original Not Worn detector remains active.

## Verification

```powershell
python -m pytest tests\test_newbackend_analysis_fixes.py tests\test_mindrove_device.py -q
node ElectronFrontEnd\src\service\taskQualityGate.test.mjs
```