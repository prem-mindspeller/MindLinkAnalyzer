import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import wsEegService from '../../service/wsEegService';
import { createFourChannelBatchCollector } from '../../service/continuousRecording.mjs';
import {
  ACTIVE_BATTERY_PROFILE,
  BATTERY_VERSION,
  PROTOCOL_PROFILE_METADATA,
  PROTOCOL_VALIDATION_STATUS,
  STIMULUS_PACK_VERSION,
  TASK_DEFINITIONS,
  TASK_IDS,
  audioProfileForTask,
  closureRevealState,
  countWords,
  inTaskAudioLocalization,
  isLanguageNoticeSection,
  pacedPassageChunk,
  profileComponentRefs,
  protocolProfileRefForTask,
  runnerProtocolFor,
  scoringThresholdsFor,
  taskPresentationFor,
  taskFormForSession,
  taskIntroduction,
  visualComparisonFrame,
  visualRouteState,
} from './optimizedBatteryConfig.mjs';
import { dutchCueAudioAssetsForForm } from './dutchCueAudioAssets.mjs';
import { scoreOptimizedTask } from './optimizedTaskScoring.mjs';
import '../../styles/taskSelection.css';

const RUNNER_PROTOCOL = runnerProtocolFor();
const COUNTDOWN_SECONDS = RUNNER_PROTOCOL.countdownSeconds;
const RESPONSE_EXCLUSION_MS = RUNNER_PROTOCOL.responseExclusionMs;
const RECORDING_CONTRACT = RUNNER_PROTOCOL.recordingContract;
// Browser speech synthesis delivers its onend event a beat after the audio
// actually finishes. A stimulus scheduled within this window of the block end
// cannot fire onend before the block finalizes and audio is cancelled, so its
// started delivery is accepted as sufficient (the audio still played).
const SPEECH_END_GRACE_MS = 6000;

const emptyAudioDeliveryAudit = ({ schedule = [], noiseRequired = false } = {}) => ({
  expectedSpeech: new Set(schedule
    .filter((event) => event.type === 'spoken_stimulus' || event.type === 'spoken_passage_onset')
    .map((event) => String(event.key))),
  scheduledSpeech: new Set(),
  startedSpeech: new Set(),
  endedSpeech: new Set(),
  expectedTones: new Set(schedule
    .filter((event) => event.type === 'tone_onset')
    .map((event) => String(event.key))),
  scheduledTones: new Set(),
  startedTones: new Set(),
  endedTones: new Set(),
  noiseRequired,
  noiseStarted: false,
  failed: new Set(),
  finalized: false,
});

const nowMs = () => (
  typeof performance !== 'undefined' && typeof performance.now === 'function'
    ? performance.now()
    : Date.now()
);

const isoNow = () => new Date().toISOString();

// Task-end cue. Four 1000 Hz beeps, identical to the eyes-closed baseline's
// completion sound (BaselineCalibration1.jsx), so participants get a clear,
// familiar signal that the scoring block has ended — e.g. when to open their
// eyes on an eyes-closed task. Uses its own short-lived AudioContext so it is
// unaffected by the task audio being stopped/cancelled at block end.
function playCueBeep(frequencyHz = 1000, durationMs = 150) {
  try {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return;
    const context = new AudioContextClass();
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    oscillator.connect(gain);
    gain.connect(context.destination);
    oscillator.frequency.value = frequencyHz;
    oscillator.type = 'sine';
    gain.gain.setValueAtTime(0.3, context.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, context.currentTime + durationMs / 1000);
    oscillator.start(context.currentTime);
    oscillator.stop(context.currentTime + durationMs / 1000);
  } catch (_) { /* audio is best-effort */ }
}

function playTaskCompletionCue() {
  for (let index = 0; index < 4; index += 1) {
    setTimeout(() => playCueBeep(1000, 150), index * 200);
  }
}

// Emphasise the ordering clause of the anomaly rule wherever it is shown, so
// participants notice the letter–hyphen–digits sequence must be in that order.
const RULE_ORDER_PHRASE = 'in that same order';
function renderRuleWithOrderEmphasis(text) {
  const value = String(text ?? '');
  const index = value.indexOf(RULE_ORDER_PHRASE);
  if (index < 0) return value;
  return [
    value.slice(0, index),
    <strong key="rule-order-emphasis">{RULE_ORDER_PHRASE}</strong>,
    value.slice(index + RULE_ORDER_PHRASE.length),
  ];
}

function normalizeAssetDescriptor(value) {
  if (typeof value === 'string') return { uri: value, sha256: null, playbackRate: 1 };
  if (!value || typeof value !== 'object') return null;
  const uri = value.uri || value.assetUri || value.asset_uri;
  if (!uri) return null;
  return {
    uri,
    sha256: value.sha256 || value.assetSha256 || value.asset_sha256 || null,
    playbackRate: Number(value.playbackRate || value.assetPlaybackRate || value.asset_playback_rate) || 1,
  };
}

function configuredAudioAsset(profile, formId, auditKey, scheduled = {}) {
  const explicit = normalizeAssetDescriptor({
    uri: scheduled.asset_uri || scheduled.assetUri,
    sha256: scheduled.asset_sha256 || scheduled.assetSha256,
    playbackRate: scheduled.asset_playback_rate || scheduled.assetPlaybackRate,
  });
  if (explicit) return explicit;

  const formAssets = profile.assetsByForm?.[formId];
  const formSpecific = normalizeAssetDescriptor(
    formAssets?.[auditKey]
      || formAssets?.[`${formId}:${auditKey}`]
      || (scheduled.type === 'spoken_passage_onset' ? formAssets : null),
  );
  if (formSpecific) return formSpecific;

  const keyed = normalizeAssetDescriptor(
    profile.assetsByStimulusKey?.[`${formId}:${auditKey}`]
      || profile.assetsByStimulusKey?.[auditKey],
  );
  if (keyed) return keyed;

  if (scheduled.target === true) {
    return normalizeAssetDescriptor({
      uri: profile.targetAssetUri,
      sha256: profile.targetAssetSha256,
    });
  }
  if (scheduled.target === false) {
    return normalizeAssetDescriptor({
      uri: profile.distractorAssetUri,
      sha256: profile.distractorAssetSha256,
    });
  }
  return normalizeAssetDescriptor({ uri: profile.assetUri, sha256: profile.assetSha256 });
}

function configuredAssetManifest(profile, formId, schedule) {
  const byAsset = new Map();
  for (const scheduled of schedule) {
    if (scheduled.type !== 'spoken_stimulus'
      && scheduled.type !== 'spoken_passage_onset'
      && scheduled.type !== 'tone_onset') continue;
    const descriptor = configuredAudioAsset(profile, formId, String(scheduled.key), scheduled);
    if (!descriptor) continue;
    const identity = `${descriptor.uri}\u0000${descriptor.sha256 || ''}`;
    const existing = byAsset.get(identity) || {
      uri: descriptor.uri,
      sha256: descriptor.sha256,
      playback_rate: descriptor.playbackRate,
      stimulus_keys: [],
    };
    existing.stimulus_keys.push(String(scheduled.key));
    byAsset.set(identity, existing);
  }
  return [...byAsset.values()];
}

function directionSymbol(orientation) {
  return { north: '↑', east: '→', south: '↓', west: '←' }[orientation] || '↑';
}

function initialResponseFor(taskId) {
  if (taskId === TASK_IDS.ANOMALY) return { anomalyTypes: [], confidence: 3 };
  return {};
}

function auditSchedule(taskId, form, definition, presentation) {
  const events = [];
  for (const taskPhase of definition.phases.slice(1)) {
    events.push({ key: `phase:${taskPhase.id}`, at: taskPhase.start, type: 'phase_boundary', phase_id: taskPhase.id });
  }
  for (const [index, spoken] of (form.spokenEvents || []).entries()) {
    events.push({ key: `speech:${index}`, at: spoken.at, type: 'spoken_stimulus', text: spoken.text });
  }
  for (const [index, tone] of (form.toneEvents || []).entries()) {
    events.push({ key: `tone:${index}`, at: tone.at, type: 'tone_onset', target: tone.target, frequency_hz: tone.frequency, duration_ms: tone.durationMs });
  }
  if (taskId === TASK_IDS.VISUOSPATIAL) {
    form.moves.forEach((move, index) => events.push({ key: `route:${index}`, at: move.at, type: 'route_turn', turn: move.turn }));
  }
  if (taskId === TASK_IDS.ANOMALY) {
    form.entries.forEach((entry, index) => events.push({
      key: `code:${index}`,
      at: entry.at ?? index * presentation.entryIntervalSeconds,
      type: 'code_entry_onset',
      stimulus_index: index,
      anomaly: Boolean(entry.type),
      anomaly_type: entry.type,
    }));
  }
  if (taskId === TASK_IDS.VISUAL_COMPARISON) {
    events.push({ key: 'mismatch_due', at: form.mismatchOnset, type: 'mismatch_reveal_due' });
  }
  if (taskId === TASK_IDS.SPEECH_NOISE) {
    events.push({
      key: 'passage',
      at: form.passageOnsetSeconds ?? presentation.passageOnsetSeconds,
      type: 'spoken_passage_onset',
      text: form.passage,
      asset_uri: form.audioAssetUri || null,
      asset_sha256: form.audioAssetSha256 || null,
      asset_playback_rate: form.audioAssetPlaybackRate || 1,
      asset_provenance: form.audioAssetProvenance || null,
    });
  }
  if (taskId === TASK_IDS.WRITTEN) {
    const chunkInterval = presentation.readingDurationSeconds / presentation.chunkCount;
    for (let index = 0; index < presentation.chunkCount; index += 1) {
      events.push({
        key: `passage_chunk:${index}`,
        at: index * chunkInterval,
        type: 'paced_text_chunk',
        chunk_index: index,
      });
    }
  }
  return events.sort((left, right) => left.at - right.at);
}

function ResponseField({ label, children }) {
  return (
    <label className="optimized-response-field">
      <span>{label}</span>
      {children}
    </label>
  );
}

function ComparisonLine({ frame, revealMismatch, revealSeconds }) {
  return (
    <div
      className="optimized-comparison-line"
      aria-label={revealMismatch ? frame.changed : frame.base}
      style={{ '--mismatch-reveal-duration': `${revealSeconds}s` }}
    >
      {[...frame.base].map((character, index) => {
        if (index !== frame.mismatchIndex) return <span key={index}>{character}</span>;
        return (
          <span
            key={index}
            className={`optimized-comparison-character${revealMismatch ? ' is-revealing' : ''}`}
            aria-hidden="true"
          >
            <span className="optimized-comparison-original">{character}</span>
            {revealMismatch && (
              <span className="optimized-comparison-replacement">{frame.changed[index]}</span>
            )}
          </span>
        );
      })}
    </div>
  );
}

function FragmentedClosureTarget({ form, reveal, fragmentOrder }) {
  return (
    <div
      className="optimized-closure-fragments"
      style={{ filter: `blur(${reveal.blurPx}px)` }}
      role="img"
      aria-label="Fragmented target embedded in visual noise"
    >
      {Array.from({ length: 16 }, (_, fragmentIndex) => {
        const row = Math.floor(fragmentIndex / 4);
        const column = fragmentIndex % 4;
        const revealRank = fragmentOrder.indexOf(fragmentIndex);
        const threshold = revealRank / 16;
        const fragmentOpacity = Math.max(
          0,
          Math.min(1, (reveal.fragmentProgress - threshold) * 20),
        ) * reveal.symbolOpacity;
        return (
          <span
            key={fragmentIndex}
            className="optimized-closure-fragment"
            aria-hidden="true"
            style={{
              clipPath: `inset(${row * 25}% ${(3 - column) * 25}% ${(3 - row) * 25}% ${column * 25}%)`,
              opacity: fragmentOpacity,
            }}
          >{form.symbol}</span>
        );
      })}
    </div>
  );
}

const OptimizedBatteryTask = ({ taskId, sessionDepth, onComplete, onBack }) => {
  const { t, i18n } = useTranslation();
  const baseDefinition = TASK_DEFINITIONS[taskId];
  const selectedLanguage = (i18n.resolvedLanguage || i18n.language || 'en').split('-')[0];
  const form = useMemo(
    () => taskFormForSession(taskId, sessionDepth, undefined, selectedLanguage),
    [taskId, sessionDepth, selectedLanguage],
  );
  const definition = useMemo(() => {
    const taskDurationSeconds = Number(form?.audioAssetTaskDurationSeconds);
    if (
      taskId !== TASK_IDS.SPEECH_NOISE
      || !Number.isFinite(taskDurationSeconds)
      || taskDurationSeconds <= baseDefinition.duration
    ) return baseDefinition;
    return {
      ...baseDefinition,
      duration: taskDurationSeconds,
      phases: baseDefinition.phases.map((phase, index, phases) => (
        index === phases.length - 1
          ? { ...phase, end: taskDurationSeconds, duration: taskDurationSeconds - phase.start }
          : phase
      )),
    };
  }, [baseDefinition, form?.audioAssetTaskDurationSeconds, taskId]);
  const audioLocalization = useMemo(
    () => inTaskAudioLocalization(taskId, form, selectedLanguage),
    [form, selectedLanguage, taskId],
  );
  const { hasDutchSpokenCueTranslation } = audioLocalization;
  const inTaskAudioLanguage = audioLocalization.language;
  const inTaskAudioTranslationStatus = audioLocalization.status;
  const presentation = useMemo(() => taskPresentationFor(taskId), [taskId]);
  const audioProfile = useMemo(() => audioProfileForTask(taskId), [taskId]);
  // Spoken cues always use a speech-synthesis profile — even on the dual task,
  // whose primary audioProfile is tones. Without this, speak() would receive the
  // tone profile and reject every "Update"/"Switch" cue as an unsupported speech
  // mode, silencing the cues and failing the audio-delivery audit.
  const speechProfile = useMemo(() => {
    const profile = taskId === TASK_IDS.SPEECH_NOISE
      ? ACTIVE_BATTERY_PROFILE.audioProfiles.speech_in_noise
      : ACTIVE_BATTERY_PROFILE.audioProfiles.spoken_stimuli;
    if (taskId === TASK_IDS.SPEECH_NOISE && form.audioAssetExpectedDeliverySeconds) {
      return {
        ...profile,
        expectedDeliverySeconds: form.audioAssetExpectedDeliverySeconds,
        settlingSeconds: Math.max(profile.settlingSeconds || 0, 8),
      };
    }
    if (!hasDutchSpokenCueTranslation) return profile;
    return {
      ...profile,
      mode: 'audio_asset_or_browser_speech_synthesis',
      language: 'nl-NL',
      assetsByStimulusKey: dutchCueAudioAssetsForForm(form),
      assetProvenance: {
        provider: 'elevenlabs',
        model_id: 'eleven_multilingual_v2',
        output_format: 'mp3_44100_128',
        voice_label: 'Will - Dutch-accent European narrator',
      },
    };
  }, [form, hasDutchSpokenCueTranslation, taskId]);
  const scoringThresholds = useMemo(() => scoringThresholdsFor(taskId), [taskId]);
  const introductions = useMemo(() => taskIntroduction(taskId, form, t), [taskId, form, t]);
  const schedule = useMemo(
    () => auditSchedule(taskId, form, definition, presentation),
    [taskId, form, definition, presentation],
  );

  const [runState, setRunState] = useState('idle');
  const [countdown, setCountdown] = useState(COUNTDOWN_SECONDS);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [response, setResponse] = useState(() => initialResponseFor(taskId));
  const [buttonRuntime, setButtonRuntime] = useState(null);

  const startClockRef = useRef(null);
  const taskTimerRef = useRef(null);
  const countdownTimerRef = useRef(null);
  const batchCollectorRef = useRef(null);
  const signalStatsRef = useRef({ total: 0, good: 0, noisy: 0, notWorn: 0, worstPoorSignal: null });
  const eventsRef = useRef([]);
  const exclusionsRef = useRef([]);
  const firedEventsRef = useRef(new Set());
  const unsubRef = useRef(null);
  const audioContextRef = useRef(null);
  const noiseSourceRef = useRef(null);
  const assetAudioRefsRef = useRef(new Set());
  const speechUtteranceRefsRef = useRef(new Set());
  const audioDeliveryRef = useRef(emptyAudioDeliveryAudit());
  const recordingRunRef = useRef(0);
  const startingRef = useRef(false);
  const finalRecordingRef = useRef(null);
  const buttonRuntimeRef = useRef(null);
  const finishingRef = useRef(false);
  const mismatchRenderedElapsedMsRef = useRef(null);
  const renderFrameRef = useRef(null);

  const comparisonMismatchDue = taskId === TASK_IDS.VISUAL_COMPARISON
    && runState === 'running'
    && elapsedSeconds >= form.mismatchOnset;

  const recordedSampleCount = useCallback(
    () => batchCollectorRef.current?.sampleCount || 0,
    [],
  );

  const getAudioContext = useCallback(() => {
    if (!audioContextRef.current) {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (AudioContextClass) {
        const context = new AudioContextClass();
        context.onstatechange = () => {
          const audit = audioDeliveryRef.current;
          if (
            audit.finalized
            || startClockRef.current == null
            || context.state === 'running'
          ) return;
          const failureKey = `audio_context_${context.state || 'not_running'}`;
          audit.failed.add(failureKey);
          eventsRef.current.push({
            type: 'audio_context_not_running',
            stimulus_key: failureKey,
            actual_elapsed_ms: Math.round(Math.max(0, nowMs() - startClockRef.current)),
            sample_index: recordedSampleCount(),
            analysis_use: 'delivery_audit_only_not_erp',
          });
        };
        audioContextRef.current = context;
      }
    }
    if (audioContextRef.current?.state === 'suspended') audioContextRef.current.resume().catch(() => {});
    return audioContextRef.current;
  }, [recordedSampleCount]);

  const playTone = useCallback((
    frequency,
    durationMs = audioProfile.durationMs,
    auditKey = null,
    plannedAt = 0,
    toneProfile = audioProfile,
    scheduled = {},
  ) => {
    const normalizedAuditKey = auditKey == null ? null : String(auditKey);
    const runToken = recordingRunRef.current;
    const audit = audioDeliveryRef.current;
    const auditIsCurrent = () => (
      recordingRunRef.current === runToken
      && audioDeliveryRef.current === audit
      && !audit.finalized
    );
    if (normalizedAuditKey && auditIsCurrent()) audit.scheduledTones.add(normalizedAuditKey);
    const pushToneMarker = (type, extra = {}) => {
      if (!normalizedAuditKey || !auditIsCurrent() || startClockRef.current == null) return;
      eventsRef.current.push({
        type,
        stimulus_key: normalizedAuditKey,
        planned_elapsed_ms: Math.round(Number(plannedAt || 0) * 1000),
        actual_elapsed_ms: Math.round(Math.max(0, nowMs() - startClockRef.current)),
        sample_index: recordedSampleCount(),
        analysis_use: 'delivery_audit_only_not_erp',
        ...extra,
      });
    };
    try {
      if (toneProfile.mode === 'premixed_audio_asset') {
        const descriptor = configuredAudioAsset(
          toneProfile,
          form.id,
          normalizedAuditKey,
          scheduled,
        );
        if (!descriptor?.uri || typeof window.Audio !== 'function') {
          throw new Error('Configured tone audio asset is unavailable');
        }
        const asset = new window.Audio(descriptor.uri);
        asset.preload = 'auto';
        asset.volume = Math.max(0, Math.min(1, Number(toneProfile.volume ?? 1)));
        assetAudioRefsRef.current.add(asset);
        asset.onplaying = () => {
          if (!auditIsCurrent()) return;
          if (normalizedAuditKey) audit.startedTones.add(normalizedAuditKey);
          pushToneMarker('tone_playback_started', {
            source_mode: toneProfile.mode,
            asset_sha256: descriptor.sha256,
          });
        };
        asset.onended = () => {
          assetAudioRefsRef.current.delete(asset);
          if (!auditIsCurrent()) return;
          if (normalizedAuditKey) audit.endedTones.add(normalizedAuditKey);
          pushToneMarker('tone_playback_ended', { source_mode: toneProfile.mode });
        };
        asset.onerror = () => {
          assetAudioRefsRef.current.delete(asset);
          if (!auditIsCurrent()) return;
          if (normalizedAuditKey) audit.failed.add(normalizedAuditKey);
          pushToneMarker('tone_playback_failed', {
            source_mode: toneProfile.mode,
            error_code: 'asset_playback_error',
          });
        };
        const playback = asset.play();
        if (playback?.catch) playback.catch((error) => {
          assetAudioRefsRef.current.delete(asset);
          if (!auditIsCurrent()) return;
          if (normalizedAuditKey) audit.failed.add(normalizedAuditKey);
          pushToneMarker('tone_playback_failed', {
            source_mode: toneProfile.mode,
            error_code: error?.message || 'asset_play_rejected',
          });
        });
        return true;
      }
      if (toneProfile.mode !== 'web_audio_oscillator') {
        throw new Error(`Unsupported tone source mode: ${toneProfile.mode || 'missing'}`);
      }
      const context = getAudioContext();
      if (!context) throw new Error('WebAudio context unavailable');
      if (context.state !== 'running') throw new Error(`WebAudio context is ${context.state || 'not running'}`);
      const oscillator = context.createOscillator();
      const gain = context.createGain();
      const resolvedDurationMs = Math.max(1, Number(durationMs || toneProfile.durationMs || 115));
      const outputGain = Math.max(0.001, Number(toneProfile.outputGain || 0.22));
      oscillator.connect(gain);
      gain.connect(context.destination);
      oscillator.type = toneProfile.waveform || 'sine';
      oscillator.frequency.value = frequency;
      gain.gain.setValueAtTime(outputGain, context.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, context.currentTime + resolvedDurationMs / 1000);
      oscillator.onended = () => {
        if (!auditIsCurrent()) return;
        if (normalizedAuditKey) audit.endedTones.add(normalizedAuditKey);
        pushToneMarker('tone_playback_ended');
      };
      oscillator.start();
      oscillator.stop(context.currentTime + resolvedDurationMs / 1000);
      if (normalizedAuditKey && auditIsCurrent()) audit.startedTones.add(normalizedAuditKey);
      pushToneMarker('tone_playback_started', {
        source_mode: toneProfile.mode,
        audio_context_time: context.currentTime,
      });
      return true;
    } catch (error) {
      if (normalizedAuditKey && auditIsCurrent()) {
        audit.failed.add(normalizedAuditKey);
        pushToneMarker('tone_playback_failed', { error_code: error?.message || 'exception' });
      }
      return false;
    }
  }, [audioProfile, form.id, getAudioContext, recordedSampleCount]);

  const speak = useCallback((text, scheduled = {}) => {
    const auditKey = String(scheduled.key || `speech:${scheduled.at || 0}:${text}`);
    const runToken = recordingRunRef.current;
    const audit = audioDeliveryRef.current;
    const auditIsCurrent = () => (
      recordingRunRef.current === runToken
      && audioDeliveryRef.current === audit
      && !audit.finalized
    );
    if (auditIsCurrent()) audit.scheduledSpeech.add(auditKey);
    const pushPlaybackMarker = (type, extra = {}) => {
      if (!auditIsCurrent() || startClockRef.current == null) return;
      eventsRef.current.push({
        type,
        stimulus_key: auditKey,
        planned_elapsed_ms: Math.round(Number(scheduled.at || 0) * 1000),
        actual_elapsed_ms: Math.round(Math.max(0, nowMs() - startClockRef.current)),
        sample_index: recordedSampleCount(),
        analysis_use: 'delivery_audit_only_not_erp',
        ...extra,
      });
    };
    try {
      const sourceMode = speechProfile.mode;
      const assetDescriptor = configuredAudioAsset(speechProfile, form.id, auditKey, scheduled);
      const canUseAsset = assetDescriptor?.uri && typeof window.Audio === 'function';
      if (canUseAsset && (
        sourceMode === 'premixed_audio_asset'
        || sourceMode === 'audio_asset_with_generated_noise'
        || sourceMode === 'audio_asset_or_browser_speech_synthesis'
      )) {
        if (!assetDescriptor?.uri) {
          throw new Error('Configured speech audio asset is unavailable');
        }
        const asset = new window.Audio(assetDescriptor.uri);
        asset.preload = 'auto';
        asset.volume = Math.max(0, Math.min(1, Number(speechProfile.volume ?? 1)));
        asset.playbackRate = Math.max(0.5, Math.min(2, assetDescriptor.playbackRate || 1));
        assetAudioRefsRef.current.add(asset);
        asset.onplaying = () => {
          if (!auditIsCurrent()) return;
          audit.startedSpeech.add(auditKey);
          if (sourceMode === 'premixed_audio_asset' && taskId === TASK_IDS.SPEECH_NOISE) audit.noiseStarted = true;
          pushPlaybackMarker('speech_playback_started', {
            source_mode: sourceMode,
            actual_source_mode: 'audio_asset',
            asset_sha256: assetDescriptor.sha256,
            asset_playback_rate: asset.playbackRate,
          });
        };
        asset.onended = () => {
          assetAudioRefsRef.current.delete(asset);
          if (!auditIsCurrent()) return;
          audit.endedSpeech.add(auditKey);
          pushPlaybackMarker('speech_playback_ended', { source_mode: sourceMode });
        };
        asset.onerror = () => {
          assetAudioRefsRef.current.delete(asset);
          if (!auditIsCurrent()) return;
          audit.failed.add(auditKey);
          pushPlaybackMarker('speech_playback_failed', {
            source_mode: sourceMode,
            error_code: 'asset_playback_error',
          });
        };
        const playback = asset.play();
        if (playback?.catch) playback.catch((error) => {
          assetAudioRefsRef.current.delete(asset);
          if (!auditIsCurrent()) return;
          audit.failed.add(auditKey);
          pushPlaybackMarker('speech_playback_failed', {
            source_mode: sourceMode,
            error_code: error?.message || 'asset_play_rejected',
          });
        });
        return true;
      }
      if (
        sourceMode !== 'browser_speech_synthesis'
        && sourceMode !== 'browser_speech_synthesis_with_generated_noise'
        && sourceMode !== 'audio_asset_or_browser_speech_synthesis'
      ) {
        throw new Error(`Unsupported speech source mode: ${sourceMode || 'missing'}`);
      }
      if (!window.speechSynthesis || !window.SpeechSynthesisUtterance || !text) {
        if (auditIsCurrent()) audit.failed.add(auditKey);
        pushPlaybackMarker('speech_playback_unavailable');
        return false;
      }
      const utterance = new window.SpeechSynthesisUtterance(text);
      utterance.lang = speechProfile.language;
      utterance.rate = speechProfile.rate;
      utterance.pitch = speechProfile.pitch;
      utterance.volume = speechProfile.volume;
      if (speechProfile.voiceId) {
        const configuredVoice = window.speechSynthesis.getVoices?.().find((voice) => (
          voice.voiceURI === speechProfile.voiceId || voice.name === speechProfile.voiceId
        ));
        if (configuredVoice) utterance.voice = configuredVoice;
      }
      // Chromium/Electron garbage-collects an utterance that is not referenced
      // after speak() returns, which silently drops its onend (and sometimes
      // onstart) event. That made the delivery audit under-count started/ended
      // speech and blocked otherwise-valid tasks. Hold a live reference until the
      // utterance settles, then release it.
      speechUtteranceRefsRef.current.add(utterance);
      utterance.onstart = () => {
        if (!auditIsCurrent()) return;
        audit.startedSpeech.add(auditKey);
        pushPlaybackMarker('speech_playback_started', {
          source_mode: sourceMode,
          actual_source_mode: 'browser_speech_synthesis',
        });
      };
      utterance.onend = () => {
        speechUtteranceRefsRef.current.delete(utterance);
        if (!auditIsCurrent()) return;
        audit.endedSpeech.add(auditKey);
        pushPlaybackMarker('speech_playback_ended', { source_mode: sourceMode });
      };
      utterance.onerror = (event) => {
        speechUtteranceRefsRef.current.delete(utterance);
        if (!auditIsCurrent()) return;
        audit.failed.add(auditKey);
        pushPlaybackMarker('speech_playback_failed', {
          source_mode: sourceMode,
          error_code: event?.error || 'unknown',
        });
      };
      window.speechSynthesis.speak(utterance);
      return true;
    } catch (error) {
      if (auditIsCurrent()) audit.failed.add(auditKey);
      pushPlaybackMarker('speech_playback_failed', { error_code: error?.message || 'exception' });
      return false;
    }
  }, [speechProfile, form.id, recordedSampleCount, taskId]);

  const startModerateNoise = useCallback(() => {
    if (taskId !== TASK_IDS.SPEECH_NOISE) return;
    const auditKey = 'speech_noise_background';
    const runToken = recordingRunRef.current;
    const audit = audioDeliveryRef.current;
    const auditIsCurrent = () => (
      recordingRunRef.current === runToken
      && audioDeliveryRef.current === audit
      && !audit.finalized
    );
    audit.noiseRequired = true;
    try {
      if (audioProfile.mode === 'premixed_audio_asset') {
        // The speech asset contains its calibrated noise bed. Its actual
        // playback callback marks both speech and noise as started.
        return;
      }
      if (
        audioProfile.mode !== 'browser_speech_synthesis_with_generated_noise'
        && audioProfile.mode !== 'audio_asset_with_generated_noise'
      ) {
        throw new Error(`Speech-in-noise source mode has no noise delivery: ${audioProfile.mode || 'missing'}`);
      }
      const noiseProfile = audioProfile.noise;
      const context = getAudioContext();
      if (!context) throw new Error('WebAudio context unavailable');
      if (context.state !== 'running') throw new Error(`WebAudio context is ${context.state || 'not running'}`);
      const frameCount = Math.max(1, Math.floor(context.sampleRate * noiseProfile.bufferSeconds));
      const buffer = context.createBuffer(1, frameCount, context.sampleRate);
      const channel = buffer.getChannelData(0);
      let seed = Number(noiseProfile.seed) >>> 0;
      for (let index = 0; index < frameCount; index += 1) {
        seed = (1664525 * seed + 1013904223) >>> 0;
        channel[index] = ((seed / 4294967296) * 2 - 1) * noiseProfile.sampleAmplitude;
      }
      const source = context.createBufferSource();
      const gain = context.createGain();
      source.buffer = buffer;
      source.loop = true;
      gain.gain.value = noiseProfile.outputGain;
      source.connect(gain);
      gain.connect(context.destination);
      source.onended = () => {
        if (!auditIsCurrent()) return;
        audit.failed.add(`${auditKey}_ended_early`);
        eventsRef.current.push({
          type: 'noise_playback_ended_early',
          stimulus_key: auditKey,
          actual_elapsed_ms: Math.round(Math.max(0, nowMs() - startClockRef.current)),
          sample_index: recordedSampleCount(),
          analysis_use: 'delivery_audit_only_not_erp',
          source_mode: audioProfile.mode,
        });
      };
      source.start();
      noiseSourceRef.current = source;
      audit.noiseStarted = true;
      if (auditIsCurrent() && startClockRef.current != null) {
        eventsRef.current.push({
          type: 'noise_playback_started',
          stimulus_key: auditKey,
          actual_elapsed_ms: Math.round(Math.max(0, nowMs() - startClockRef.current)),
          sample_index: recordedSampleCount(),
          analysis_use: 'delivery_audit_only_not_erp',
          source_mode: audioProfile.mode,
        });
      }
    } catch (error) {
      if (auditIsCurrent()) audit.failed.add(auditKey);
      eventsRef.current.push({
        type: 'noise_playback_failed',
        stimulus_key: auditKey,
        actual_elapsed_ms: startClockRef.current == null ? 0 : Math.round(Math.max(0, nowMs() - startClockRef.current)),
        sample_index: recordedSampleCount(),
        analysis_use: 'delivery_audit_only_not_erp',
        source_mode: audioProfile.mode,
        error_code: error?.message || 'exception',
      });
    }
  }, [audioProfile, getAudioContext, recordedSampleCount, taskId]);

  const stopAudio = useCallback(() => {
    try { noiseSourceRef.current?.stop(); } catch (_) { /* already stopped */ }
    noiseSourceRef.current = null;
    for (const asset of assetAudioRefsRef.current) {
      try {
        asset.pause();
        asset.removeAttribute('src');
        asset.load();
      } catch (_) { /* already stopped or detached */ }
    }
    assetAudioRefsRef.current.clear();
    try { window.speechSynthesis?.cancel(); } catch (_) { /* ignore */ }
    speechUtteranceRefsRef.current.clear();
  }, []);

  const stopSubscriptions = useCallback(() => {
    if (unsubRef.current) unsubRef.current();
    unsubRef.current = null;
  }, []);

  const clearTimers = useCallback(() => {
    clearInterval(taskTimerRef.current);
    clearInterval(countdownTimerRef.current);
    taskTimerRef.current = null;
    countdownTimerRef.current = null;
  }, []);

  const recordSignal = useCallback((poorSignal) => {
    const value = Number(poorSignal);
    if (!Number.isFinite(value)) return;
    const stats = signalStatsRef.current;
    stats.total += 1;
    stats.worstPoorSignal = stats.worstPoorSignal == null ? value : Math.max(stats.worstPoorSignal, value);
    if (value >= 200) stats.notWorn += 1;
    else if (value < 25) stats.good += 1;
    else stats.noisy += 1;
  }, []);

  const attachRecording = useCallback(() => {
    const unsubRawMultiBatch = wsEegService.on('rawMultiBatch', (batch) => {
      batchCollectorRef.current?.appendBatch(
        batch?.samples,
        batch?.receivedAtMs,
        batch?.streamStartSampleIndex,
      );
    });
    const unsubSignal = wsEegService.on('eegData', (data) => recordSignal(data?.poorSignal));
    recordSignal(wsEegService.getPoorSignal());
    unsubRef.current = () => {
      unsubRawMultiBatch();
      unsubSignal();
    };
  }, [recordSignal]);

  const fireScheduledEvent = useCallback((scheduled, actualElapsedMs) => {
    const speechUsesAudioAsset = (
      speechProfile.mode === 'premixed_audio_asset'
      || speechProfile.mode === 'audio_asset_with_generated_noise'
      || (
        speechProfile.mode === 'audio_asset_or_browser_speech_synthesis'
        && configuredAudioAsset(speechProfile, form.id, String(scheduled.key), scheduled)?.uri
      )
    );
    eventsRef.current.push({
      ...scheduled,
      planned_elapsed_ms: Math.round(scheduled.at * 1000),
      actual_elapsed_ms: Math.round(actualElapsedMs),
      sample_index: recordedSampleCount(),
      marker_basis: scheduled.type === 'spoken_stimulus' || scheduled.type === 'spoken_passage_onset'
        ? speechUsesAudioAsset
          ? 'html_audio_dispatch'
          : 'speech_synthesis_dispatch'
        : scheduled.type === 'tone_onset'
          ? audioProfile.mode === 'premixed_audio_asset'
            ? 'html_audio_dispatch'
            : 'web_audio_dispatch'
          : 'recording_clock',
    });
    if (scheduled.type === 'tone_onset') playTone(
      scheduled.frequency_hz,
      scheduled.duration_ms,
      scheduled.key,
      scheduled.at,
      audioProfile,
      scheduled,
    );
    if (scheduled.type === 'spoken_stimulus' || scheduled.type === 'spoken_passage_onset') speak(scheduled.text, scheduled);
  }, [audioProfile, form.id, playTone, recordedSampleCount, speak, speechProfile]);

  const runDueEvents = useCallback((elapsedMs) => {
    for (const scheduled of schedule) {
      if (firedEventsRef.current.has(scheduled.key) || scheduled.at * 1000 > elapsedMs) continue;
      firedEventsRef.current.add(scheduled.key);
      fireScheduledEvent(scheduled, elapsedMs);
    }
  }, [fireScheduledEvent, schedule]);

  const finishRecording = useCallback((runtime = { detected: false }) => {
    if (finishingRef.current) return;
    finishingRef.current = true;
    const actualElapsedMs = Math.min(
      definition.duration * 1000,
      Math.max(0, nowMs() - (startClockRef.current || nowMs())),
    );
    clearTimers();
    stopSubscriptions();
    runDueEvents(actualElapsedMs);

    const audioAudit = audioDeliveryRef.current;
    audioAudit.finalized = true;
    // Stimuli scheduled in the block's final seconds cannot reliably fire onend
    // before finalize; accept started-only delivery for those specific keys.
    const blockEndMs = definition.duration * 1000;
    const speechEndWaivedKeys = new Set(
      schedule
        .filter((event) => (
          (event.type === 'spoken_stimulus' || event.type === 'spoken_passage_onset')
          && (blockEndMs - event.at * 1000) <= SPEECH_END_GRACE_MS
        ))
        .map((event) => String(event.key)),
    );
    const incompleteSpeechKeys = [...audioAudit.expectedSpeech].filter(
      (key) => (
        !audioAudit.scheduledSpeech.has(key)
        || !audioAudit.startedSpeech.has(key)
        || (!audioAudit.endedSpeech.has(key) && !speechEndWaivedKeys.has(key))
      ),
    );
    const incompleteToneKeys = [...audioAudit.expectedTones].filter(
      (key) => (
        !audioAudit.scheduledTones.has(key)
        || !audioAudit.startedTones.has(key)
        || !audioAudit.endedTones.has(key)
      ),
    );
    const failedAudioKeys = [...audioAudit.failed];
    const noiseDeliveryComplete = !audioAudit.noiseRequired || audioAudit.noiseStarted;
    const deliveryProfile = audioAudit.expectedSpeech.size ? speechProfile : audioProfile;
    const audioDelivery = {
      profile_id: PROTOCOL_PROFILE_METADATA.components.audio.id,
      profile_version: PROTOCOL_PROFILE_METADATA.components.audio.version,
      source_mode: deliveryProfile.mode,
      speech_source_mode: audioAudit.expectedSpeech.size ? speechProfile.mode : null,
      tone_source_mode: audioAudit.expectedTones.size ? audioProfile.mode : null,
      stimulus_language: inTaskAudioLanguage,
      translation_status: inTaskAudioTranslationStatus,
      acoustically_calibrated: deliveryProfile.acousticallyCalibrated === true,
      declared_asset_uri: deliveryProfile.assetUri || null,
      declared_asset_sha256: deliveryProfile.assetSha256 || null,
      declared_asset_manifest: configuredAssetManifest(deliveryProfile, form.id, schedule),
      voice_asset_provenance: deliveryProfile.assetProvenance || form.audioAssetProvenance || null,
      expected_delivery_seconds: deliveryProfile.expectedDeliverySeconds ?? null,
      settling_seconds: deliveryProfile.settlingSeconds ?? null,
      expected_speech_count: audioAudit.expectedSpeech.size,
      scheduled_speech_count: audioAudit.scheduledSpeech.size,
      started_speech_count: audioAudit.startedSpeech.size,
      ended_speech_count: audioAudit.endedSpeech.size,
      incomplete_speech_keys: incompleteSpeechKeys,
      expected_tone_count: audioAudit.expectedTones.size,
      scheduled_tone_count: audioAudit.scheduledTones.size,
      started_tone_count: audioAudit.startedTones.size,
      ended_tone_count: audioAudit.endedTones.size,
      incomplete_tone_keys: incompleteToneKeys,
      background_noise_required: audioAudit.noiseRequired,
      background_noise_started: audioAudit.noiseStarted,
      failed_audio_keys: failedAudioKeys,
      speech_end_waived_keys: [...speechEndWaivedKeys].filter(
        (key) => audioAudit.startedSpeech.has(key) && !audioAudit.endedSpeech.has(key),
      ),
      protocol_complete: (
        incompleteSpeechKeys.length === 0
        && incompleteToneKeys.length === 0
        && noiseDeliveryComplete
        && failedAudioKeys.length === 0
      ),
    };
    incompleteSpeechKeys.forEach((key) => eventsRef.current.push({
      type: 'speech_incomplete_at_task_end',
      stimulus_key: key,
      actual_elapsed_ms: Math.round(actualElapsedMs),
      sample_index: recordedSampleCount(),
      analysis_use: 'delivery_audit_only_not_erp',
    }));
    incompleteToneKeys.forEach((key) => eventsRef.current.push({
      type: 'tone_incomplete_at_task_end',
      stimulus_key: key,
      actual_elapsed_ms: Math.round(actualElapsedMs),
      sample_index: recordedSampleCount(),
      analysis_use: 'delivery_audit_only_not_erp',
    }));
    stopAudio();
    // Signal the end of the scoring block so participants know to stop and (on
    // eyes-closed tasks) open their eyes — matches the baseline completion cue.
    playTaskCompletionCue();

    const interactionRuntime = buttonRuntimeRef.current || {};
    const resolvedRuntime = taskId === TASK_IDS.VISUAL_COMPARISON
      ? {
        ...runtime,
        ...interactionRuntime,
        mismatchRenderedElapsedMs: mismatchRenderedElapsedMsRef.current,
      }
      : { ...runtime, ...interactionRuntime };
    const responseElapsedMs = resolvedRuntime.responseElapsedMs ?? actualElapsedMs;
    const hasButtonResponse = resolvedRuntime.detected === true;
    const scoreEndMs = hasButtonResponse
      ? Math.max(0, responseElapsedMs - RESPONSE_EXCLUSION_MS)
      : actualElapsedMs;
    if (hasButtonResponse) {
      if (!exclusionsRef.current.some((interval) => (
        interval.reason === 'button_response_and_post_response_state'
      ))) {
        exclusionsRef.current.push({
          reason: 'button_response_and_post_response_state',
          start_elapsed_ms: scoreEndMs,
          end_elapsed_ms: actualElapsedMs,
        });
      }
      if (!eventsRef.current.some((event) => event.type === 'button_response')) {
        eventsRef.current.push({
          type: 'button_response',
          actual_elapsed_ms: Math.round(responseElapsedMs),
          sample_index: resolvedRuntime.responseSampleIndex ?? recordedSampleCount(),
        });
      }
    }
    eventsRef.current.push({ type: 'task_end', actual_elapsed_ms: Math.round(actualElapsedMs), sample_index: recordedSampleCount() });
    eventsRef.current.push({ type: 'response_cue', actual_elapsed_ms: Math.round(actualElapsedMs), sample_index: recordedSampleCount() });

    const capturedRecording = batchCollectorRef.current?.snapshot() || {
      samples: [],
      transport_segments: [],
      sample_rate_hz: 500,
      invalid_sample_count: 0,
      max_contiguous_transport_seconds: 0,
      transport_gap_count: 0,
    };
    const scoredRecording = batchCollectorRef.current?.snapshot({ endBeforeMs: scoreEndMs }) || capturedRecording;
    finalRecordingRef.current = {
      samples: scoredRecording.samples,
      capturedSampleCount: capturedRecording.samples.length,
      transportSegments: scoredRecording.transport_segments,
      sampleRateHz: scoredRecording.sample_rate_hz,
      invalidChannelSampleCount: scoredRecording.invalid_sample_count,
      maxContiguousTransportSeconds: scoredRecording.max_contiguous_transport_seconds,
      transportGapCount: scoredRecording.transport_gap_count,
      actualElapsedMs,
      scoreEndMs,
      runtime: { ...resolvedRuntime, responseElapsedMs },
      audioDelivery,
    };
    setElapsedSeconds(actualElapsedMs / 1000);
    setButtonRuntime({ ...resolvedRuntime, responseElapsedMs });

    if (taskId === TASK_IDS.VISUAL_COMPARISON) {
      const behavioralEvidence = scoreOptimizedTask(taskId, form, {}, finalRecordingRef.current.runtime);
      setRunState('saving');
      const metadata = buildMetadata(finalRecordingRef.current, behavioralEvidence);
      Promise.resolve(onComplete(finalRecordingRef.current.samples, { ...signalStatsRef.current }, metadata)).catch(() => {});
      return;
    }
    setRunState('response');
  // buildMetadata deliberately resolves at callback time from immutable refs.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [audioProfile, clearTimers, definition.duration, form, onComplete, recordedSampleCount, runDueEvents, schedule, speechProfile, stopAudio, stopSubscriptions, taskId]);

  const beginRecording = useCallback(() => {
    signalStatsRef.current = { total: 0, good: 0, noisy: 0, notWorn: 0, worstPoorSignal: null };
    recordingRunRef.current += 1;
    audioDeliveryRef.current = emptyAudioDeliveryAudit({
      schedule,
      noiseRequired: taskId === TASK_IDS.SPEECH_NOISE,
    });
    eventsRef.current = [{ type: 'task_start', actual_elapsed_ms: 0, sample_index: 0 }];
    exclusionsRef.current = [];
    firedEventsRef.current = new Set();
    finalRecordingRef.current = null;
    buttonRuntimeRef.current = null;
    setButtonRuntime(null);
    finishingRef.current = false;
    mismatchRenderedElapsedMsRef.current = null;
    if (renderFrameRef.current != null) window.cancelAnimationFrame(renderFrameRef.current);
    renderFrameRef.current = null;
    startClockRef.current = nowMs();
    const deviceInfo = wsEegService.getDeviceInfo?.() || {};
    batchCollectorRef.current = createFourChannelBatchCollector({
      sampleRateHz: Number(deviceInfo.sampleRate) || 500,
      startedAtMs: startClockRef.current,
    });
    setElapsedSeconds(0);
    setRunState('running');
    attachRecording();
    startModerateNoise();
    runDueEvents(0);
    taskTimerRef.current = setInterval(() => {
      const elapsedMs = Math.max(0, nowMs() - startClockRef.current);
      runDueEvents(elapsedMs);
      setElapsedSeconds(Math.min(definition.duration, elapsedMs / 1000));
      if (elapsedMs >= definition.duration * 1000) finishRecording({ detected: false, timedOut: true });
    }, 50);
  }, [attachRecording, definition.duration, finishRecording, runDueEvents, schedule, startModerateNoise, taskId]);

  const listenToInstructions = useCallback(() => {
    try {
      if (!window.speechSynthesis || !window.SpeechSynthesisUtterance) return;
      window.speechSynthesis.cancel();
      const utterance = new window.SpeechSynthesisUtterance(
        introductions.map((section) => section.body).join(' '),
      );
      utterance.lang = i18n.resolvedLanguage || i18n.language || 'en';
      utterance.rate = 0.9;
      window.speechSynthesis.speak(utterance);
    } catch (_) { /* optional accessibility audio */ }
  }, [i18n.language, i18n.resolvedLanguage, introductions]);

  const startTask = useCallback(() => {
    if (startingRef.current || runState !== 'idle') return;
    startingRef.current = true;
    try { window.speechSynthesis?.cancel(); } catch (_) { /* optional accessibility audio */ }
    getAudioContext();
    setRunState('countdown');
    let remaining = COUNTDOWN_SECONDS;
    setCountdown(remaining);
    const countdownAudio = ACTIVE_BATTERY_PROFILE.audioProfiles.countdown;
    playTone(
      countdownAudio.frequencyHz,
      countdownAudio.durationMs,
      null,
      0,
      countdownAudio,
    );
    countdownTimerRef.current = setInterval(() => {
      remaining -= 1;
      if (remaining > 0) {
        setCountdown(remaining);
        playTone(
          countdownAudio.frequencyHz,
          countdownAudio.durationMs,
          null,
          0,
          countdownAudio,
        );
      } else {
        clearInterval(countdownTimerRef.current);
        countdownTimerRef.current = null;
        beginRecording();
      }
    }, 1000);
  }, [beginRecording, getAudioContext, playTone, runState]);

  const abortTask = useCallback(() => {
    audioDeliveryRef.current.finalized = true;
    recordingRunRef.current += 1;
    startingRef.current = false;
    clearTimers();
    stopSubscriptions();
    stopAudio();
    if (renderFrameRef.current != null) window.cancelAnimationFrame(renderFrameRef.current);
    renderFrameRef.current = null;
    mismatchRenderedElapsedMsRef.current = null;
    batchCollectorRef.current = null;
    finalRecordingRef.current = null;
    buttonRuntimeRef.current = null;
    onBack();
  }, [clearTimers, onBack, stopAudio, stopSubscriptions]);

  const handleDetection = useCallback(() => {
    if (runState !== 'running' || buttonRuntimeRef.current?.detected) return;
    const responseElapsedMs = Math.min(
      definition.duration * 1000,
      Math.max(0, nowMs() - startClockRef.current),
    );
    const responseSampleIndex = recordedSampleCount();
    const runtime = {
      detected: true,
      responseElapsedMs,
      responseSampleIndex,
      timedOut: false,
    };
    buttonRuntimeRef.current = runtime;
    setButtonRuntime(runtime);
    exclusionsRef.current.push({
      reason: 'button_response_and_post_response_state',
      start_elapsed_ms: Math.max(0, responseElapsedMs - RESPONSE_EXCLUSION_MS),
      end_elapsed_ms: definition.duration * 1000,
    });
    eventsRef.current.push({
      type: 'button_response',
      actual_elapsed_ms: Math.round(responseElapsedMs),
      sample_index: responseSampleIndex,
    });
  }, [definition.duration, recordedSampleCount, runState]);

  useEffect(() => {
    if (!comparisonMismatchDue || mismatchRenderedElapsedMsRef.current != null) return undefined;
    renderFrameRef.current = window.requestAnimationFrame(() => {
      renderFrameRef.current = null;
      if (startClockRef.current == null || finishingRef.current) return;
      const renderedElapsedMs = Math.max(0, nowMs() - startClockRef.current);
      mismatchRenderedElapsedMsRef.current = renderedElapsedMs;
      eventsRef.current.push({
        type: 'mismatch_rendered_onset',
        planned_elapsed_ms: Math.round(form.mismatchOnset * 1000),
        actual_elapsed_ms: Math.round(renderedElapsedMs),
        sample_index: recordedSampleCount(),
        analysis_use: 'audit_only_not_erp',
      });
    });
    return () => {
      if (renderFrameRef.current != null) window.cancelAnimationFrame(renderFrameRef.current);
      renderFrameRef.current = null;
    };
  }, [comparisonMismatchDue, form.mismatchOnset, recordedSampleCount]);

  function buildMetadata(recording, behavioralEvidence) {
    const deviceInfo = wsEegService.getDeviceInfo?.() || {};
    const sampleRateHz = Number(deviceInfo.sampleRate);
    return {
      contract_version: 'mindspeller_continuous_task_result_v1',
      battery_version: BATTERY_VERSION,
      stimulus_pack_version: STIMULUS_PACK_VERSION,
      audio_pack_version: PROTOCOL_PROFILE_METADATA.components.audio.version,
      rubric_set_version: PROTOCOL_PROFILE_METADATA.components.rubrics.version,
      threshold_set_version: PROTOCOL_PROFILE_METADATA.components.thresholds.version,
      protocol_validation_status: PROTOCOL_VALIDATION_STATUS,
      protocol_profile: PROTOCOL_PROFILE_METADATA,
      protocol_profile_ref: protocolProfileRefForTask(taskId, undefined, definition.duration),
      protocol_components: profileComponentRefs(),
      protocol_valid: recording.audioDelivery?.protocol_complete === true,
      protocol_invalid_reasons: recording.audioDelivery?.protocol_complete === true
        ? []
        : ['missing_incomplete_or_failed_audio_delivery'],
      canonical_task_id: taskId,
      task_number: definition.number,
      canonical_task_name: definition.name,
      session_depth: sessionDepth,
      form_id: form.id,
      form_language: form.language || ACTIVE_BATTERY_PROFILE.language,
      form_language_pack_status: form.language_pack_status || 'candidate_source_english',
      in_task_audio_language: inTaskAudioLanguage,
      in_task_audio_translation_status: inTaskAudioTranslationStatus,
      eye_state: definition.eyeState,
      matched_baseline: definition.baseline,
      sample_rate_hz: recording.sampleRateHz || (Number.isFinite(sampleRateHz) ? sampleRateHz : null),
      planned_recording_duration_ms: definition.duration * 1000,
      actual_recording_duration_ms: Math.round(recording.actualElapsedMs),
      eeg_score_end_ms: Math.round(recording.scoreEndMs),
      phases: definition.phases.map((taskPhase) => ({
        phase_id: taskPhase.id,
        label: taskPhase.label,
        start_elapsed_ms: taskPhase.start * 1000,
        end_elapsed_ms: taskPhase.end * 1000,
        planned_duration_ms: taskPhase.duration * 1000,
      })),
      event_markers: [...eventsRef.current].sort((left, right) => (left.actual_elapsed_ms || 0) - (right.actual_elapsed_ms || 0)),
      exclusion_intervals: [...exclusionsRef.current],
      recording: {
        continuous_block: true,
        device: deviceInfo.device || null,
        channels: Array.isArray(deviceInfo.channels)
          ? [...deviceInfo.channels]
          : [...RECORDING_CONTRACT.requiredChannels],
        analysis_model: 'rolling_time_series_only',
        window_seconds: RECORDING_CONTRACT.rollingWindowSeconds,
        overlap_fraction: RECORDING_CONTRACT.overlapFraction,
        minimum_contiguous_clean_seconds: RECORDING_CONTRACT.minimumContiguousCleanSeconds,
        captured_sample_count: recording.capturedSampleCount,
        scored_sample_count: recording.samples.length,
        response_exclusion_ms: recording.runtime.detected ? RESPONSE_EXCLUSION_MS : 0,
        required_channels: [...RECORDING_CONTRACT.requiredChannels],
        transport_segments: recording.transportSegments,
        max_contiguous_transport_seconds: recording.maxContiguousTransportSeconds,
        transport_gap_count: recording.transportGapCount,
        invalid_channel_sample_count: recording.invalidChannelSampleCount,
        audio_delivery: recording.audioDelivery,
      },
      reference_conditions: taskId === TASK_IDS.DUAL_TASK
        ? ['eyes_closed', TASK_IDS.WORKING_MEMORY, TASK_IDS.AUDITORY_COUNT]
        : [definition.baseline],
      behavioral_evidence: behavioralEvidence,
      scientific_guardrails: {
        eeg_is_task_contextual: true,
        no_direct_onet_band_mapping: true,
        no_erp_or_stimulus_locked_analysis: true,
        multimodal_abilities_require_behavior: true,
      },
      completed_at: isoNow(),
    };
  }

  const submitResponse = useCallback((event) => {
    event.preventDefault();
    if (!finalRecordingRef.current) return;
    const behavioralEvidence = scoreOptimizedTask(taskId, form, response, buttonRuntime || finalRecordingRef.current.runtime);
    const metadata = buildMetadata(finalRecordingRef.current, behavioralEvidence);
    setRunState('saving');
    Promise.resolve(onComplete(finalRecordingRef.current.samples, { ...signalStatsRef.current }, metadata)).catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [buttonRuntime, form, onComplete, response, taskId]);

  useEffect(() => () => {
    audioDeliveryRef.current.finalized = true;
    recordingRunRef.current += 1;
    startingRef.current = false;
    clearTimers();
    stopSubscriptions();
    stopAudio();
    if (renderFrameRef.current != null) window.cancelAnimationFrame(renderFrameRef.current);
    try { audioContextRef.current?.close(); } catch (_) { /* ignore */ }
  }, [clearTimers, stopAudio, stopSubscriptions]);

  if (!definition) return null;

  const currentPhase = definition.phases.find((taskPhase) => (
    elapsedSeconds >= taskPhase.start && elapsedSeconds < taskPhase.end
  )) || definition.phases.at(-1);
  const elapsedPct = Math.min(100, Math.round((elapsedSeconds / definition.duration) * 100));
  const taskName = t(`optimizedBattery.taskNames.${taskId}`, { defaultValue: definition.name });
  const eyeState = t(`optimizedBattery.words.eyes.${definition.eyeState}`, { defaultValue: definition.eyeState });
  const phaseLabel = t(
    `optimizedBattery.phaseLabels.${taskId}.${currentPhase.id}`,
    { defaultValue: currentPhase.label },
  );

  if (runState === 'idle') {
    return (
      <div className="task-runner-card optimized-task-card">
        <p className="optimized-task-kicker">{t('optimizedBattery.runner.candidateKicker', { defaultValue: 'Candidate/pilot · Mind Mission {{number}} · {{formId}}', number: definition.number, formId: form.id })}</p>
        <h2 className="task-runner-name">{t('taskRunner.readInstruction')}</h2>
        <div className="task-runner-badges">
          <span className={`task-eyes-badge eyes-${definition.eyeState}`}>{t('optimizedBattery.runner.eyesBadge', { defaultValue: 'Eyes {{eyeState}}', eyeState })}</span>
          <span className="task-eyes-badge task-duration-badge">{t('optimizedBattery.runner.durationBadge', { defaultValue: '⏱ {{duration}}s EEG', duration: definition.duration })}</span>
          <span className="task-eyes-badge optimized-language-badge">{t('optimizedBattery.runner.stimulusLanguage', { defaultValue: 'Stimulus: {{language}}', language: form.language || 'en' })}</span>
        </div>
        <div className="task-runner-sound-notice">🔊 {t('taskRunner.soundNotice')}</div>
        <div className="task-runner-intro">
          {introductions
            .filter((section) => !isLanguageNoticeSection(section.id) || selectedLanguage !== 'en')
            .map((section) => (
              <div
                key={section.id}
                className={`task-runner-intro-section${isLanguageNoticeSection(section.id) ? ' task-runner-intro-notice' : ''}`}
              >
                {section.title && <h3 className="task-runner-intro-title">{section.title}</h3>}
                {String(section.body || '').split('\n\n').map((paragraph, index) => (
                  <p key={index}>{renderRuleWithOrderEmphasis(paragraph)}</p>
                ))}
              </div>
            ))}
        </div>
        <details className="optimized-guardrail-details">
          <summary>{t('optimizedBattery.runner.aboutMeasurementLabel', { defaultValue: 'About this measurement' })}</summary>
          <p className="optimized-guardrail">{t('optimizedBattery.runner.guardrail', { defaultValue: 'EEG features are Mind-Mission-contextual candidate evidence. Behavioral validity and signal quality are checked separately.' })}</p>
        </details>
        <div className="task-runner-actions">
          <button type="button" className="task-runner-btn-back" onClick={onBack}>{t('taskRunner.cancel')}</button>
          <button type="button" className="task-runner-btn-back" onClick={listenToInstructions}>{t('optimizedBattery.listen', { defaultValue: 'Listen to instructions' })}</button>
          <button type="button" className="task-runner-btn-start" onClick={startTask}>{t('taskRunner.start')}</button>
        </div>
      </div>
    );
  }

  if (runState === 'countdown') {
    return (
      <div className="task-runner-card task-runner-countdown-screen">
        <p className="task-runner-get-ready">{t('optimizedBattery.runner.getReady', { defaultValue: 'Get ready · Eyes {{eyeState}}', eyeState })}</p>
        <div className="task-runner-big-countdown">{countdown}</div>
        <p className="task-runner-countdown-caption">{t('optimizedBattery.runner.countdownCaption', { defaultValue: 'The uninterrupted Mind Mission begins after the final beep.' })}</p>
      </div>
    );
  }

  if (runState === 'running') {
    const route = taskId === TASK_IDS.VISUOSPATIAL ? visualRouteState(form, elapsedSeconds) : null;
    const anomalyEntry = taskId === TASK_IDS.ANOMALY
      ? form.entries[Math.min(form.entries.length - 1, Math.floor(elapsedSeconds / 2))]
      : null;
    const writtenChunk = taskId === TASK_IDS.WRITTEN
      && elapsedSeconds < presentation.readingDurationSeconds
      ? pacedPassageChunk(form, elapsedSeconds)
      : null;
    const closureReveal = taskId === TASK_IDS.CLOSURE
      ? closureRevealState(form, elapsedSeconds)
      : null;
    const comparisonFrame = taskId === TASK_IDS.VISUAL_COMPARISON
      ? visualComparisonFrame(form, elapsedSeconds)
      : null;
    return (
      <div className={`task-runner-card task-runner-phase phase-recording optimized-running optimized-${definition.type}`}>
        <div className="optimized-running-header">
          <span className="task-runner-phase-badge">{t('optimizedBattery.runner.continuousEeg', { defaultValue: '● Continuous EEG' })}</span>
          <span>{phaseLabel}</span>
        </div>

        {definition.eyeState === 'closed' && (
          <div className="optimized-eyes-closed-cue">
            <span>{t('optimizedBattery.runner.eyesClosed')}</span>
            <small>{t('optimizedBattery.runner.eyesClosedCue')}</small>
          </div>
        )}

        {taskId === TASK_IDS.VISUOSPATIAL && route && (
          <div className="optimized-route-wrap" aria-label={t('optimizedBattery.runner.routeGridAria', { defaultValue: 'Five by five route grid' })}>
            <div className="optimized-route-column-labels" aria-hidden="true">
              {[1, 2, 3, 4, 5].map((column) => <span key={column}>{column}</span>)}
            </div>
            <div className="optimized-route-grid-row">
              <div className="optimized-route-row-labels" aria-hidden="true">
                {[1, 2, 3, 4, 5].map((rowNumber) => <span key={rowNumber}>{rowNumber}</span>)}
              </div>
              <div className="optimized-route-grid">
                {Array.from({ length: 25 }, (_, index) => {
                  const x = index % 5;
                  const y = Math.floor(index / 5);
                  const active = x === route.x && y === route.y;
                  return (
                    <div
                      key={index}
                      aria-label={`Row ${y + 1}, column ${x + 1}${active ? `, facing ${route.orientation}` : ''}`}
                      className={`optimized-route-cell${active ? ' active' : ''}`}
                    >{active ? directionSymbol(route.orientation) : ''}</div>
                  );
                })}
              </div>
            </div>
            <p>{t('optimizedBattery.runner.routeHint')}</p>
          </div>
        )}

        {taskId === TASK_IDS.ANOMALY && anomalyEntry && (
          <div className="optimized-code-stimulus">
            <small>{renderRuleWithOrderEmphasis(form.rule)}</small>
            <strong>{anomalyEntry.value}</strong>
            <p>{t('optimizedBattery.runner.anomalyHint')}</p>
          </div>
        )}

        {taskId === TASK_IDS.VISUAL_COMPARISON && comparisonFrame && (
          <div className="optimized-comparison-stimulus">
            <div>{comparisonFrame.base}</div>
            <ComparisonLine
              frame={comparisonFrame}
              revealMismatch={comparisonMismatchDue}
              revealSeconds={form.mismatchRevealSeconds}
            />
            <button
              type="button"
              className="optimized-detect-button"
              onClick={handleDetection}
              disabled={buttonRuntime?.detected === true}
            >{buttonRuntime?.detected ? t('optimizedBattery.runner.responseRegistered') : t('optimizedBattery.runner.detectMismatch')}</button>
          </div>
        )}

        {taskId === TASK_IDS.CLOSURE && closureReveal && (
          <div className="optimized-closure-stimulus">
            <FragmentedClosureTarget
              form={form}
              reveal={closureReveal}
              fragmentOrder={form.revealSchedule?.fragmentOrder || presentation.fragmentOrder}
            />
            <div className="optimized-noise-layer" style={{ opacity: closureReveal.noiseOpacity }} />
            <button
              type="button"
              className="optimized-detect-button"
              onClick={handleDetection}
              disabled={!closureReveal.responseEnabled || buttonRuntime?.detected === true}
            >{
              buttonRuntime?.detected
                ? t('optimizedBattery.runner.responseRegistered')
                : closureReveal.responseEnabled ? t('optimizedBattery.runner.recognized') : t('optimizedBattery.runner.searching')
            }</button>
          </div>
        )}

        {taskId === TASK_IDS.WRITTEN && (
          <div className="optimized-paced-reading">
            {writtenChunk
              ? <p>{writtenChunk}</p>
              : <><strong>{t('optimizedBattery.runner.silentSynthesis')}</strong><p>{t('optimizedBattery.runner.writtenHint')}</p></>}
          </div>
        )}

        <div className="task-runner-progress-wrap">
          <div className="task-runner-progress-bar" style={{ width: `${elapsedPct}%` }} />
          <span className="task-runner-progress-text">{Math.ceil(definition.duration - elapsedSeconds)}s</span>
        </div>
        <button type="button" className="task-runner-btn-abort" onClick={abortTask}>{t('taskRunner.abort')}</button>
      </div>
    );
  }

  if (runState === 'saving') {
    return (
      <div className="task-runner-card optimized-saving-card" aria-live="polite">
        <div className="optimized-saving-spinner" />
        <h2>{t('optimizedBattery.runner.savingTitle')}</h2>
        <p>{t('optimizedBattery.runner.savingHint')}</p>
      </div>
    );
  }

  const wordCount = countWords(response.summary);
  const writtenLengthValid = (
    wordCount >= scoringThresholds.summaryMinimumWords
    && wordCount <= scoringThresholds.summaryMaximumWords
  );
  return (
    <form className="task-runner-card optimized-response-card" onSubmit={submitResponse}>
      <p className="optimized-task-kicker">{t('optimizedBattery.runner.responseKicker')}</p>
      <h2>{taskName}</h2>
      <p>{t('optimizedBattery.runner.responseHint')}</p>

      {taskId === TASK_IDS.NUMERICAL && (
        <ResponseField label={t('optimizedBattery.responses.finalValue')}>
          <input type="number" required value={response.finalValue || ''} onChange={(event) => setResponse({ ...response, finalValue: event.target.value })} />
        </ResponseField>
      )}
      {taskId === TASK_IDS.WORKING_MEMORY && (
        <ResponseField label={t('optimizedBattery.responses.finalSequence')}>
          <input required value={response.finalSequence || ''} onChange={(event) => setResponse({ ...response, finalSequence: event.target.value })} />
        </ResponseField>
      )}
      {taskId === TASK_IDS.AUDITORY_COUNT && (
        <ResponseField label={t('optimizedBattery.responses.highToneCount')}>
          <input type="number" min="0" required value={response.targetCount || ''} onChange={(event) => setResponse({ ...response, targetCount: event.target.value })} />
        </ResponseField>
      )}
      {taskId === TASK_IDS.SEMANTIC && (
        <>
          <ResponseField label={t('optimizedBattery.responses.firstPrinciple')}>
            <select required value={response.ruleOne || ''} onChange={(event) => setResponse({ ...response, ruleOne: event.target.value })}>
              <option value="">{t('optimizedBattery.responses.select')}</option>
              {form.ruleOptions.map((option) => <option key={option}>{option}</option>)}
            </select>
          </ResponseField>
          <ResponseField label={t('optimizedBattery.responses.secondPrinciple')}>
            <select required value={response.ruleTwo || ''} onChange={(event) => setResponse({ ...response, ruleTwo: event.target.value })}>
              <option value="">{t('optimizedBattery.responses.select')}</option>
              {form.secondRuleOptions.map((option) => <option key={option}>{option}</option>)}
            </select>
          </ResponseField>
          <ResponseField label={t('optimizedBattery.responses.ruleSwitchDetected')}>
            <select required value={response.switchDetected || ''} onChange={(event) => setResponse({ ...response, switchDetected: event.target.value })}>
              <option value="">{t('optimizedBattery.responses.select')}</option><option value="yes">{t('optimizedBattery.responses.yes')}</option><option value="no">{t('optimizedBattery.responses.no')}</option>
            </select>
          </ResponseField>
        </>
      )}
      {taskId === TASK_IDS.VISUOSPATIAL && (
        <div className="optimized-response-grid">
          <ResponseField label={t('optimizedBattery.responses.finalColumn')}><input type="number" min="1" max="5" required value={response.x == null ? '' : Number(response.x) + 1} onChange={(event) => setResponse({ ...response, x: Number(event.target.value) - 1 })} /></ResponseField>
          <ResponseField label={t('optimizedBattery.responses.finalRow')}><input type="number" min="1" max="5" required value={response.y == null ? '' : Number(response.y) + 1} onChange={(event) => setResponse({ ...response, y: Number(event.target.value) - 1 })} /></ResponseField>
          <ResponseField label={t('optimizedBattery.responses.finalOrientation')}>
            <select required value={response.orientation || ''} onChange={(event) => setResponse({ ...response, orientation: event.target.value })}>
              <option value="">{t('optimizedBattery.responses.select')}</option>{['north', 'east', 'south', 'west'].map((option) => <option key={option} value={option}>{t(`optimizedBattery.words.directions.${option}`, { defaultValue: option })}</option>)}
            </select>
          </ResponseField>
        </div>
      )}
      {taskId === TASK_IDS.IDEATION && (
        <ResponseField label={t('optimizedBattery.responses.ideas')}>
          <textarea rows="8" required value={response.ideas || ''} onChange={(event) => setResponse({ ...response, ideas: event.target.value })} />
        </ResponseField>
      )}
      {taskId === TASK_IDS.DUAL_TASK && (
        <div className="optimized-response-grid">
          <ResponseField label={t('optimizedBattery.responses.highToneCount')}><input type="number" min="0" required value={response.targetCount || ''} onChange={(event) => setResponse({ ...response, targetCount: event.target.value })} /></ResponseField>
          <ResponseField label={t('optimizedBattery.responses.finalNumber')}><input type="number" required value={response.finalValue || ''} onChange={(event) => setResponse({ ...response, finalValue: event.target.value })} /></ResponseField>
        </div>
      )}
      {taskId === TASK_IDS.ANOMALY && (
        <>
          <ResponseField label={t('optimizedBattery.responses.anomalyCount')}><input type="number" min="0" required value={response.anomalyCount || ''} onChange={(event) => setResponse({ ...response, anomalyCount: event.target.value })} /></ResponseField>
          <fieldset className="optimized-checkboxes">
            <legend>{t('optimizedBattery.responses.anomalyTypes')}</legend>
            {['extra_letter', 'wrong_order', 'missing_separator', 'missing_digit', 'wrong_separator'].map((type) => (
              <label key={type}><input type="checkbox" checked={response.anomalyTypes.includes(type)} onChange={(event) => {
                const values = event.target.checked ? [...response.anomalyTypes, type] : response.anomalyTypes.filter((value) => value !== type);
                setResponse({ ...response, anomalyTypes: values });
              }} /> {t(`optimizedBattery.anomalyTypes.${type}`, { defaultValue: type.replaceAll('_', ' ') })}</label>
            ))}
          </fieldset>
          <ResponseField label={t('optimizedBattery.responses.confidence', { confidence: response.confidence })}><input type="range" min="1" max="5" value={response.confidence} onChange={(event) => setResponse({ ...response, confidence: event.target.value })} /></ResponseField>
        </>
      )}
      {taskId === TASK_IDS.CLOSURE && (
        <ResponseField label={t('optimizedBattery.responses.recognizedTarget')}>
          <select required value={response.target || ''} onChange={(event) => setResponse({ ...response, target: event.target.value })}>
            <option value="">{t('optimizedBattery.responses.select')}</option>{form.options.map((option) => <option key={option}>{option}</option>)}
          </select>
        </ResponseField>
      )}
      {taskId === TASK_IDS.SPEECH_NOISE && (
        <>
          <ResponseField label={t('optimizedBattery.responses.mainInterpretation')}>
            <select required value={response.mainIdea || ''} onChange={(event) => setResponse({ ...response, mainIdea: event.target.value })}>
              <option value="">{t('optimizedBattery.responses.select')}</option>{form.mainIdeaOptions.map((option) => <option key={option}>{option}</option>)}
            </select>
          </ResponseField>
          <ResponseField label={form.keyDetailQuestion}><input required value={response.keyDetail || ''} onChange={(event) => setResponse({ ...response, keyDetail: event.target.value })} /></ResponseField>
          <ResponseField label={t('optimizedBattery.speechInNoise.paraphrase', { defaultValue: 'Give one concise paraphrase of the passage.' })}><textarea rows="4" required value={response.paraphrase || ''} onChange={(event) => setResponse({ ...response, paraphrase: event.target.value })} /></ResponseField>
        </>
      )}
      {taskId === TASK_IDS.WRITTEN && (
        <>
          <ResponseField label={t('optimizedBattery.responses.mainIdea')}>
            <select required value={response.mainIdea || ''} onChange={(event) => setResponse({ ...response, mainIdea: event.target.value })}>
              <option value="">{t('optimizedBattery.responses.select')}</option>{form.mainIdeaOptions.map((option) => <option key={option}>{option}</option>)}
            </select>
          </ResponseField>
          <ResponseField label={t('optimizedBattery.responses.summary', { minimum: scoringThresholds.summaryMinimumWords, maximum: scoringThresholds.summaryMaximumWords, count: wordCount })}>
            <textarea rows="7" required value={response.summary || ''} onChange={(event) => setResponse({ ...response, summary: event.target.value })} />
          </ResponseField>
          {!writtenLengthValid && (
            <p className="optimized-response-warning">
              {t('optimizedBattery.responses.summaryWarning', { minimum: scoringThresholds.summaryMinimumWords, maximum: scoringThresholds.summaryMaximumWords })}
            </p>
          )}
        </>
      )}

      {buttonRuntime?.timedOut && (taskId === TASK_IDS.CLOSURE) && (
        <p className="optimized-response-warning">{t('optimizedBattery.responses.recognitionTimeout')}</p>
      )}
      <div className="task-runner-actions">
        <button type="submit" className="task-runner-btn-start" disabled={taskId === TASK_IDS.WRITTEN && !writtenLengthValid}>{t('optimizedBattery.responses.save')}</button>
      </div>
    </form>
  );
};

export default OptimizedBatteryTask;
