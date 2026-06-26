const MAX_NOISY_BASELINE_RATIO = 0.15;
const MAX_NOISY_BASELINE_EVENTS = 4;

export function evaluateBaselineSignalStats(signalStats = {}) {
  const total = Number(signalStats?.total || 0);
  const goodCount = Number(signalStats?.good || 0);
  const noisyCount = Number(signalStats?.noisy || 0);
  const notWornCount = Number(signalStats?.notWorn || 0);
  const noisyRatio = total > 0 ? noisyCount / total : 0;

  const acceptable = (
    total > 0 &&
    notWornCount === 0 &&
    noisyCount <= MAX_NOISY_BASELINE_EVENTS &&
    noisyRatio <= MAX_NOISY_BASELINE_RATIO
  );

  let reason = 'Signal stable during baseline recording';
  if (total === 0) {
    reason = 'No live signal status samples were available during baseline recording';
  } else if (notWornCount > 0) {
    reason = 'Signal was not worn during baseline recording';
  } else if (noisyCount > MAX_NOISY_BASELINE_EVENTS || noisyRatio > MAX_NOISY_BASELINE_RATIO) {
    reason = 'Signal was noisy too often during baseline recording';
  }

  return {
    acceptable,
    total,
    goodCount,
    noisyCount,
    notWornCount,
    noisyRatio,
    worstPoorSignal: signalStats?.worstPoorSignal ?? null,
    reason,
  };
}
