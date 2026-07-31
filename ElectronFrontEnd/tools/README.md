# Task-battery asset tooling

## Speech-in-noise calibrated audio (Task 11)

`speech_in_noise_mixer.py` / `build_speech_in_noise_assets.py` build the
premixed, SNR-calibrated audio that `optimizedBatteryProfile.mjs`'s
`speech_in_noise` profile now points at. See `test_speech_in_noise_mixer.py`
for the DSP tests.

The three passages are pre-extracted as plain text in `narration/*_text.txt`
(source of truth: `SPEECH_BASE_FORMS` in `../src/components/tasks/optimizedBatteryConfig.mjs`).
The mixer only needs mono 16-bit PCM WAV narration — it doesn't care which TTS
engine produced it. Two options:

### Option A: Piper TTS (better voice quality, needs setup)

```bash
cd ElectronFrontEnd/tools
python3 -m venv .venv
source .venv/bin/activate
pip install piper-tts

mkdir -p voices
python3 -m piper.download_voices --download-dir voices en_US-lessac-medium
```

`.venv/` and `voices/` are gitignored (large, regenerable, environment-specific).

```bash
source .venv/bin/activate
for id in speech_a speech_b speech_c; do
  cat "narration/${id}_text.txt" | python3 -m piper \
    -m voices/en_US-lessac-medium.onnx \
    -f "narration/${id}.wav"
done
```

Other voices: `python3 -m piper.download_voices --download-dir voices <name>`
lists/downloads alternatives (e.g. a different `en_US-*` speaker). Speaking
rate can be adjusted with `--length-scale` (>1.0 slower, <1.0 faster) if a
narration's duration should track the task's `expectedDeliverySeconds` more
closely.

### Option B: Windows SAPI (no install, Windows-only)

The narration currently checked into `narration/*.wav` was generated this way
(`Microsoft David Desktop` voice), since Piper isn't available in every
environment this repo is built in. SAPI's WAV output at 22050 Hz mono 16-bit
PCM matches the mixer's expected format exactly — no conversion needed.
`synthesize_speech_a.ps1` regenerates all three from the current
`SPEECH_BASE_FORMS` text (edit its `$texts` map if the passages change, or
adapt it to read straight from `narration/*_text.txt`):

```powershell
& "./synthesize_speech_a.ps1"
```

List installed voices with:

```powershell
Add-Type -AssemblyName System.Speech
(New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices() |
  ForEach-Object { $_.VoiceInfo.Name }
```

### Mix to a calibrated SNR

```bash
python3 build_speech_in_noise_assets.py --narration-dir ./narration
```

Prints a `speech_in_noise` config block (`assetsByForm`, `nominalSnrDb`,
`acousticallyCalibrated: true`) ready to paste into `optimizedBatteryProfile.mjs`,
and writes the WAVs to `../src/assets/audio/` (copied into `dist/audio/` at
build time by the `copy-webpack-plugin` entry in `webpack.config.js`).

Re-running with the same narration, seed, and target SNR reproduces the
previous output byte-for-byte (same sha256) — useful for confirming nothing
drifted after a dependency bump.

### Regenerating after a passage or SNR change

If `SPEECH_BASE_FORMS` changes, re-export the text first:

```bash
cd ../src/components/tasks
node --input-type=module -e "
import { TASK_IDS, FORM_REGISTRY_FOR_TESTS } from './optimizedBatteryConfig.mjs';
import { writeFileSync } from 'node:fs';
for (const f of FORM_REGISTRY_FOR_TESTS[TASK_IDS.SPEECH_NOISE]) {
  writeFileSync('../../../tools/narration/' + f.id + '_text.txt', f.passage + '\n');
}
"
```

then repeat the Piper/SAPI + mixing steps above with a new target SNR via
`--target-snr-db`.

### Narration length vs. playbackRate

`speech_in_noise.playbackRate` in `optimizedBatteryProfile.mjs` slows down
in-browser delivery (Chromium/Electron time-stretches premixed_audio_asset
playback while preserving pitch). Task 11's block is a fixed 120 seconds, so
at a given playbackRate the raw narration must be short enough that
`onset (0.5s) + narration_duration / playbackRate` finishes with a safe
margin (aim for >= 8s) before the block ends — otherwise the passage gets cut
off mid-sentence and the attempt fails its audio-delivery check.

The checked-in `narration/*.wav` (206–216 words each, ~76–85s at normal
speed) leave a comfortable ~19–30s margin at the current playbackRate (0.85).
If `playbackRate` drops further or the passages grow substantially longer,
recompute the margin above first.
