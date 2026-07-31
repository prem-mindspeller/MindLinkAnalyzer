# Regenerates Task 11 (speech-in-noise) narration WAVs via Windows SAPI,
# reading each form's text from narration/<id>_text.txt (source of truth:
# SPEECH_BASE_FORMS in ../src/components/tasks/optimizedBatteryConfig.mjs —
# see tools/README.md for how to re-export those text files after an edit).
# Run this script from anywhere; paths below are relative to this file.
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$synth.SelectVoice("Microsoft David Desktop")
$synth.Rate = 0
$format = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(22050, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)

$narrationDir = Join-Path $PSScriptRoot "narration"
foreach ($formId in @("speech_a", "speech_b", "speech_c")) {
  $textPath = Join-Path $narrationDir "$formId`_text.txt"
  $outPath = Join-Path $narrationDir "$formId.wav"
  $text = (Get-Content -Raw $textPath).Trim()
  $synth.SetOutputToWaveFile($outPath, $format)
  $synth.Speak($text)
  $synth.SetOutputToNull()
  Write-Output "$formId -> $outPath"
}
