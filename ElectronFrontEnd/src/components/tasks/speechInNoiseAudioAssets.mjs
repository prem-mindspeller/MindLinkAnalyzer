// Generated narration assets for the currently reachable Task-11 form.
// Playback rates and any language-specific task window are explicit in the
// audit record so narration is never cut off by the recording timer.
const asset = (uri, sha256, playbackRate, taskDurationSeconds = null, expectedDeliverySeconds = null) => Object.freeze({
  uri,
  sha256,
  playbackRate,
  taskDurationSeconds,
  expectedDeliverySeconds,
  provider: 'elevenlabs',
  modelId: 'eleven_multilingual_v2',
  outputFormat: 'mp3_44100_128',
  voiceLabel: 'Will - Conversational European Narrator',
});

const SPEECH_A_ASSETS = Object.freeze({
  en: asset(new URL('../../assets/audio/speech-in-noise/en/speech_a.mp3', import.meta.url).href, '7d2c83f09b0029449ce68917ae4beb919489e03f8907a0d4f5df45108a170d71', 1),
  nl: asset(new URL('../../assets/audio/speech-in-noise/nl/speech_a.mp3', import.meta.url).href, 'ce0c61eac5a58af4d779a9f9b27909bc9ad2584bb992565f4939ec305bd1deb0', 0.8, 165, 157),
  de: asset(new URL('../../assets/audio/speech-in-noise/de/speech_a.mp3', import.meta.url).href, '958f7ad4214966c1e74cedc06674cbc3877c603e6cf1b79a12704e65dd5dbf97', 1.203),
  fr: asset(new URL('../../assets/audio/speech-in-noise/fr/speech_a.mp3', import.meta.url).href, 'fa8fb6ca231c94c5b47684e5a910c31c585434a95ac5fff367854b033ce11f1b', 1.086),
  es: asset(new URL('../../assets/audio/speech-in-noise/es/speech_a.mp3', import.meta.url).href, '0e12c08cb0c95423ba35c47f94852a92985824839f4df19294c1ba543a3e21cd', 1.2),
  it: asset(new URL('../../assets/audio/speech-in-noise/it/speech_a.mp3', import.meta.url).href, 'c3f87a483062c4e7ddb322ff644f3a74fa2d2a4c8f7f9d1e67afb8dc633ee073', 1.196),
  pt: asset(new URL('../../assets/audio/speech-in-noise/pt/speech_a.mp3', import.meta.url).href, 'ddb3ebf141a0fafc92b57f3dc1a0bc615200baa362e21c62d6945e7df56bc714', 1.137),
  hi: asset(new URL('../../assets/audio/speech-in-noise/hi/speech_a.mp3', import.meta.url).href, 'a8d3edd76bedf3a3215ccae3f908fba7915f112ae24c87251c71900a69306c0a', 1.208),
  ar: asset(new URL('../../assets/audio/speech-in-noise/ar/speech_a.mp3', import.meta.url).href, '8ca5068827eff8f277047f52fc3acbca51049a7b245b3306e91bf91913e21c94', 1.099),
  ja: asset(new URL('../../assets/audio/speech-in-noise/ja/speech_a.mp3', import.meta.url).href, '30775723441944636c646b9abb1ce6e7b8612200b772a3066c876f169c0900f3', 1.16),
});

export function speechInNoiseAudioAsset(language, formId) {
  if (formId !== 'speech_a') return null;
  const locale = String(language || 'en').toLowerCase().split('-')[0];
  return SPEECH_A_ASSETS[locale] || SPEECH_A_ASSETS.en;
}
