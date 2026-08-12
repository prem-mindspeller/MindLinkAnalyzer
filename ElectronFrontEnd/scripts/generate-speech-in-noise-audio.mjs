import { createHash } from 'node:crypto';
import { mkdir, readFile, stat, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { TASK_IDS, taskFormForSession } from '../src/components/tasks/optimizedBatteryConfig.mjs';
import {
  SPEECH_IN_NOISE_SUPPORTED_LANGUAGES,
  localizedSpeechInNoiseForm,
} from '../src/components/tasks/speechInNoiseLanguagePacks.mjs';

const currentDirectory = dirname(fileURLToPath(import.meta.url));
const frontendDirectory = resolve(currentDirectory, '..');
const repositoryDirectory = resolve(frontendDirectory, '..');
const outputDirectory = resolve(frontendDirectory, 'src/assets/audio/speech-in-noise');
const voiceId = 'SVmtrm5iuquj8zKn5ZMg'; // Will — neutral European narrator
const modelId = 'eleven_multilingual_v2';
const outputFormat = 'mp3_44100_128';

const envPath = resolve(repositoryDirectory, 'newBackend/.env');
const env = await readFile(envPath, 'utf8');
const apiKeyMatch = env.match(/^\s*MDSP_ELEVENLABS_API\s*=\s*(.+?)\s*$/m);
if (!apiKeyMatch?.[1]) throw new Error('MDSP_ELEVENLABS_API is missing from newBackend/.env');
const apiKey = apiKeyMatch[1];

const sha256 = (buffer) => createHash('sha256').update(buffer).digest('hex');
const estimatedDurationMs = (byteLength) => Math.round((byteLength * 8 * 1000) / 128000);

async function remainingCharacters() {
  const response = await fetch('https://api.elevenlabs.io/v1/user/subscription', {
    headers: { 'xi-api-key': apiKey },
  });
  if (!response.ok) throw new Error(`ElevenLabs subscription lookup failed (${response.status})`);
  const subscription = await response.json();
  return Number(subscription.character_limit) - Number(subscription.character_count);
}

async function createAudio(language, text) {
  const response = await fetch(
    `https://api.elevenlabs.io/v1/text-to-speech/${voiceId}?output_format=${outputFormat}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'xi-api-key': apiKey },
      body: JSON.stringify({
        text,
        model_id: modelId,
        voice_settings: {
          stability: 0.65,
          similarity_boost: 0.75,
          style: 0,
          use_speaker_boost: true,
          speed: 1.1,
        },
      }),
    },
  );
  if (!response.ok) throw new Error(`ElevenLabs synthesis failed for ${language} (${response.status})`);
  return Buffer.from(await response.arrayBuffer());
}

const sourceForm = taskFormForSession(TASK_IDS.SPEECH_NOISE, 'session_3');
const forms = SPEECH_IN_NOISE_SUPPORTED_LANGUAGES.map((language) => ({
  language,
  form: localizedSpeechInNoiseForm(sourceForm, language),
}));
const requiredCharacters = forms.reduce((total, entry) => total + entry.form.passage.length, 0);
const availableCharacters = await remainingCharacters();
if (availableCharacters < requiredCharacters) {
  throw new Error(`ElevenLabs allowance is insufficient: ${availableCharacters} available, ${requiredCharacters} required`);
}

const manifest = {
  version: 'speech_in_noise_audio_candidate.1',
  provider: 'elevenlabs',
  model_id: modelId,
  voice_id: voiceId,
  output_format: outputFormat,
  noise_delivery: 'seeded_web_audio_nominal_snr_8db',
  acoustically_calibrated: false,
  assets: {},
};

for (const { language, form } of forms) {
  const relativePath = `${language}/${form.id}.mp3`;
  const outputPath = resolve(outputDirectory, relativePath);
  await mkdir(dirname(outputPath), { recursive: true });
  let audio = await readFile(outputPath).catch(() => null);
  if (audio) {
    console.log(`Reused ${language}/${form.id}.mp3`);
  } else {
    audio = await createAudio(language, form.passage);
    await writeFile(outputPath, audio);
    console.log(`Generated ${language}/${form.id}.mp3 (${form.passage.length} characters)`);
  }
  const fileInfo = await stat(outputPath);
  manifest.assets[language] = {
    form_id: form.id,
    path: relativePath,
    sha256: sha256(audio),
    character_count: form.passage.length,
    byte_length: fileInfo.size,
    estimated_duration_ms: estimatedDurationMs(fileInfo.size),
    language_pack_status: form.language_pack_status,
  };
}

await writeFile(
  resolve(outputDirectory, 'manifest.json'),
  `${JSON.stringify(manifest, null, 2)}\n`,
  'utf8',
);
