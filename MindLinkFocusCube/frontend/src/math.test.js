import { describe, expect, it } from 'vitest';
import {
  brainShellPoint,
  cubeHeightFromAttention,
  particleParamsFromBands,
  prefrontalWeight,
} from './math.js';

describe('cubeHeightFromAttention', () => {
  it('maps low and high attention to drop and lift bounds', () => {
    expect(cubeHeightFromAttention(0)).toBeCloseTo(-1.4);
    expect(cubeHeightFromAttention(1)).toBeCloseTo(2.4);
  });
});

describe('particleParamsFromBands', () => {
  it('binds blue particles to alpha and pink particles to beta/gamma', () => {
    const params = particleParamsFromBands({ alpha: 0.75, betaGamma: 0.25 });

    expect(params.blue.opacity).toBeGreaterThan(params.pink.opacity);
    expect(params.blue.activeCount).toBeGreaterThan(params.pink.activeCount);
  });
});

describe('brainShellPoint', () => {
  it('creates a top-down brain shell with separated hemispheres and a narrow midline', () => {
    const left = brainShellPoint(0.25, 0.5, 'left');
    const right = brainShellPoint(0.25, 0.5, 'right');

    expect(left.x).toBeLessThan(-0.08);
    expect(right.x).toBeGreaterThan(0.08);
    expect(Math.abs(left.z)).toBeLessThan(0.18);
    expect(Math.abs(right.z)).toBeLessThan(0.18);
  });
});

describe('prefrontalWeight', () => {
  it('weights anterior/top brain positions higher than posterior positions', () => {
    const anterior = prefrontalWeight({ x: 0.15, y: 1.1 });
    const posterior = prefrontalWeight({ x: 0.15, y: -1.1 });

    expect(anterior).toBeGreaterThan(0.7);
    expect(posterior).toBeLessThan(0.3);
  });
});
