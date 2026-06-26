import assert from 'node:assert/strict';

import { evaluateBaselineSignalStats } from './baselineQualityGate.mjs';

{
  const result = evaluateBaselineSignalStats({
    total: 20,
    good: 19,
    noisy: 1,
    notWorn: 0,
    worstPoorSignal: 30,
  });

  assert.equal(result.acceptable, true);
}

{
  const result = evaluateBaselineSignalStats({
    total: 20,
    good: 10,
    noisy: 8,
    notWorn: 2,
    worstPoorSignal: 200,
  });

  assert.equal(result.acceptable, false);
  assert.equal(result.notWornCount, 2);
  assert.match(result.reason, /not worn/i);
}

{
  const result = evaluateBaselineSignalStats({
    total: 20,
    good: 12,
    noisy: 8,
    notWorn: 0,
    worstPoorSignal: 80,
  });

  assert.equal(result.acceptable, false);
  assert.equal(result.noisyCount, 8);
  assert.match(result.reason, /noisy/i);
}
