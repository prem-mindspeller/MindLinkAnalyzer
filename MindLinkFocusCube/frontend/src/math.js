export function clamp(value, min = 0, max = 1) {
  return Math.min(max, Math.max(min, Number.isFinite(value) ? value : 0));
}

export function cubeHeightFromAttention(attention) {
  const value = clamp(attention);
  return -1.4 + value * 3.8;
}

export function gameAttentionFromPayload(payload = {}) {
  const device = payload.device ?? {};
  const focus = payload.focus ?? {};
  const progress = Number(focus.baselineProgress ?? device.baselineProgress ?? 0);
  const stableFrames = Number(device.contactStableFrames ?? 0);
  const requiredFrames = Math.max(1, Number(device.contactRequiredStableFrames ?? 1));
  const quality = Number(payload.quality ?? 0);
  const ready = payload.mode === 'device'
    && device.worn === true
    && progress >= 1
    && stableFrames >= requiredFrames
    && quality >= 0.35;

  if (!ready) {
    return 0;
  }

  const value = clamp(Number(payload.attention ?? 0));
  const deadband = 0.22;
  if (value <= deadband) {
    return 0;
  }
  return clamp((value - deadband) / (1 - deadband));
}

export function lerp(current, target, amount) {
  return current + (target - current) * clamp(amount, 0, 1);
}

export function particleParamsFromBands(normalized = {}) {
  const alpha = clamp(normalized.alpha);
  const betaGamma = clamp(normalized.betaGamma);

  return {
    blue: {
      activeCount: Math.round(3500 + alpha * 1500),
      opacity: 0.62 + alpha * 0.36,
      size: 3.2 + alpha * 3.4,
    },
    pink: {
      activeCount: Math.round(3000 + betaGamma * 2000),
      opacity: 0.58 + betaGamma * 0.40,
      size: 3.0 + betaGamma * 3.8,
    },
  };
}

function lowFrequencyNoise(x, y) {
  return (
    Math.sin(x * 2.1 + y * 0.7) * 0.045 +
    Math.sin(x * -1.3 + y * 2.6 + 1.7) * 0.035 +
    Math.cos(x * 3.2 - y * 1.4) * 0.025
  );
}

export function brainShellPoint(angleUnit, radiusUnit, hemisphere = 'left') {
  const angle = angleUnit * Math.PI * 2;
  const side = hemisphere === 'left' ? -1 : 1;
  const radial = 0.18 + clamp(radiusUnit) * 0.82;
  const pinch = 1 - Math.abs(Math.sin(angle)) * 0.1;
  const anteriorBulge = 1 + Math.max(0, Math.sin(angle)) * 0.18;
  const posteriorTaper = 1 - Math.max(0, -Math.sin(angle)) * 0.16;
  const xRadius = 0.86 * pinch;
  const yRadius = 1.26 * anteriorBulge * posteriorTaper;
  const midlineGap = 0.18;
  const localX = Math.cos(angle) * xRadius * radial;
  const localY = Math.sin(angle) * yRadius * radial;
  const x = side * midlineGap + side * Math.abs(localX);
  const y = localY + lowFrequencyNoise(localX, localY);
  const z = lowFrequencyNoise(x * 1.8, y * 1.8) * 0.9;

  return { x, y, z };
}

export function prefrontalWeight(point) {
  const yWeight = clamp((point.y + 0.35) / 1.45);
  const centerWeight = 1 - clamp(Math.abs(point.x) / 1.35);
  return clamp(yWeight * 0.78 + centerWeight * 0.22);
}
