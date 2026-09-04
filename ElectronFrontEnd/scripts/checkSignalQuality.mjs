// checkSignalQuality.mjs
//
// Standalone signal-quality monitor. Connects directly to the same local
// backend WebSocket the app uses (ws://localhost:8000/ws) and evaluates the
// live signal with the exact same client-side gate the task runner uses
// (evaluateRecordingSignal from taskQualityGate.mjs), but without being tied
// to a single task's fixed 60-180s recording window. Run it for as long as
// you want — while just wearing the headset, with no task or app UI involved
// at all — to tell apart a genuine headset/skin-contact problem from an
// app-side bug (e.g. audio-delivery timing) that only shows up during a task.
//
// Usage:
//   node scripts/checkSignalQuality.mjs
//   node scripts/checkSignalQuality.mjs --duration 300   # stop after 5 minutes
//   node scripts/checkSignalQuality.mjs --interval 10    # print a line every 10s
//   node scripts/checkSignalQuality.mjs --url ws://localhost:8000/ws
//
// Requires the Python backend (newBackend) already running and the headset
// already connected — connect it from the app's Live EEG Reading step first,
// then leave the app open (or close it) and run this script separately.
// Press Ctrl+C to stop early; a final report prints either way.

import { evaluateRecordingSignal } from '../src/service/taskQualityGate.mjs';
import { runnerProtocolFor } from '../src/components/tasks/optimizedBatteryConfig.mjs';

const args = process.argv.slice(2);
function argValue(flag, fallback) {
  const index = args.indexOf(flag);
  if (index === -1 || index === args.length - 1) return fallback;
  return args[index + 1];
}

const wsUrl = argValue('--url', 'ws://localhost:8000/ws');
const durationSeconds = Number(argValue('--duration', '0')); // 0 = run until Ctrl+C
const reportIntervalSeconds = Math.max(1, Number(argValue('--interval', '20')));

// Same classification the task runner uses in OptimizedBatteryTask.jsx's
// recordSignal(): good < 25, noisy 25-199, not worn >= 200 (poorSignal, lower
// is better). Kept here as plain constants since recordSignal() itself lives
// inside a React component and isn't exported for reuse.
const GOOD_THRESHOLD = 25;
const NOT_WORN_THRESHOLD = 200;

// The backend's real "contiguous clean seconds" check scores actual
// multi-channel EEG samples, which this script never sees. The longest-good-
// streak figure below is a local approximation built from the same 1 Hz
// poorSignal feed the app itself uses for its own client-side gate — useful
// as a same-ballpark signal, not a guaranteed match to the backend's verdict.
const MIN_CONTIGUOUS_CLEAN_SECONDS = runnerProtocolFor().recordingContract.minimumContiguousCleanSeconds;

const stats = { total: 0, good: 0, noisy: 0, notWorn: 0, worstPoorSignal: null };
let currentGoodStreak = 0;
let longestGoodStreak = 0;
let startedAt = null;

function recordSample(poorSignal) {
  const value = Number(poorSignal);
  if (!Number.isFinite(value)) return null;
  if (startedAt == null) startedAt = Date.now();
  stats.total += 1;
  stats.worstPoorSignal = stats.worstPoorSignal == null
    ? value
    : Math.max(stats.worstPoorSignal, value);

  let category;
  if (value >= NOT_WORN_THRESHOLD) {
    stats.notWorn += 1;
    category = 'not worn';
  } else if (value < GOOD_THRESHOLD) {
    stats.good += 1;
    category = 'good';
  } else {
    stats.noisy += 1;
    category = 'noisy';
  }

  if (category === 'good') {
    currentGoodStreak += 1;
    longestGoodStreak = Math.max(longestGoodStreak, currentGoodStreak);
  } else {
    currentGoodStreak = 0;
  }
  return { category, value };
}

function pct(count, total) {
  return total > 0 ? `${((count / total) * 100).toFixed(1)}%` : '0.0%';
}

function printLiveLine(sample) {
  const elapsedSeconds = stats.total;
  process.stdout.write(
    `[t=${elapsedSeconds}s] poorSignal=${sample.value} (${sample.category}) `
    + `· good=${stats.good} noisy=${stats.noisy} notWorn=${stats.notWorn} `
    + `· goodStreak=${currentGoodStreak}s (longest=${longestGoodStreak}s)\n`,
  );
}

function printReport() {
  const result = evaluateRecordingSignal(stats);
  const contiguousCleanOk = longestGoodStreak >= MIN_CONTIGUOUS_CLEAN_SECONDS;

  console.log('\n──────────────────────────────────────────────');
  console.log('Signal quality report');
  console.log('──────────────────────────────────────────────');
  console.log(`Samples:            ${stats.total}s`);
  console.log(`Good:               ${stats.good}s (${pct(stats.good, stats.total)})`);
  console.log(`Noisy:              ${stats.noisy}s (${pct(stats.noisy, stats.total)})`);
  console.log(`Not worn:           ${stats.notWorn}s (${pct(stats.notWorn, stats.total)})`);
  console.log(`Worst poorSignal:   ${stats.worstPoorSignal ?? 'n/a'}`);
  console.log(`Noisy allowance:    ${result.noisyAllowance}s`);
  console.log(
    `Longest good streak: ${longestGoodStreak}s `
    + `(needs >= ${MIN_CONTIGUOUS_CLEAN_SECONDS}s — local approximation of the `
    + `backend's contiguous-clean check, not the same computation)`,
  );
  console.log('──────────────────────────────────────────────');
  console.log(`Client-side gate (evaluateRecordingSignal): ${result.acceptable ? 'PASS' : 'FAIL'}`);
  console.log(`  Reason: ${result.reason}`);
  console.log(`Local contiguous-clean approximation:       ${contiguousCleanOk ? 'PASS' : 'FAIL'}`);
  console.log('──────────────────────────────────────────────\n');
}

let ws;
let closedByUs = false;

function connect() {
  ws = new WebSocket(wsUrl);

  ws.addEventListener('open', () => {
    console.log(`Connected to ${wsUrl}. Recording live signal quality — Ctrl+C to stop.\n`);
  });

  ws.addEventListener('message', (event) => {
    let msg;
    try {
      msg = JSON.parse(event.data);
    } catch {
      return;
    }
    if (msg.type !== 'eeg_data') return;
    const sample = recordSample(msg.poorSignal);
    if (sample) printLiveLine(sample);
  });

  ws.addEventListener('close', () => {
    if (closedByUs) return;
    console.log('WebSocket closed — reconnecting in 2s (is the backend running and the device connected?)...');
    setTimeout(connect, 2000);
  });

  ws.addEventListener('error', () => {
    // onclose fires right after; the reconnect loop there is sufficient.
  });
}

connect();

const summaryTimer = setInterval(() => {
  if (stats.total > 0 && stats.total % reportIntervalSeconds === 0) printReport();
}, 1000);

function shutdown() {
  closedByUs = true;
  clearInterval(summaryTimer);
  try { ws?.close(); } catch { /* already closed */ }
  printReport();
  process.exit(0);
}

if (durationSeconds > 0) setTimeout(shutdown, durationSeconds * 1000);
process.on('SIGINT', shutdown);
