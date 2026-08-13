const LOCALIZED_CUE_LANGUAGES = new Set(['en', 'nl']);

export function hasPendingInTaskAudioTranslation(language) {
  return !LOCALIZED_CUE_LANGUAGES.has(String(language || 'en').toLowerCase().split('-')[0]);
}
