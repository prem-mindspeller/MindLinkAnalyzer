
export const REPETITION_PREFERENCE_KEY = 'taskRepetitionDisabled';

// Session 1 establishes the participant's first reference profile and has no
// earlier run to be compared against, so its repetition requirement stands.
export const MIN_PROTOCOL_SESSION_FOR_CHOICE = 2;

function defaultStorage() {
  try {
    return globalThis.sessionStorage || null;
  } catch {
    return null;
  }
}

function readJson(storage, key) {
  try {
    const raw = storage?.getItem?.(key);
    return raw == null ? null : JSON.parse(raw);
  } catch {
    return null;
  }
}

export function canDisableRepetition(protocolSession) {
  return Number(protocolSession) >= MIN_PROTOCOL_SESSION_FOR_CHOICE;
}

/**
 * Whether repetition is waived for *this* protocol session. A waiver recorded
 * against a different session number is ignored rather than migrated, so the
 * stricter default always wins when the two disagree.
 */
export function isRepetitionDisabled(storage = defaultStorage(), protocolSession = 1) {
  if (!canDisableRepetition(protocolSession)) return false;
  const stored = readJson(storage, REPETITION_PREFERENCE_KEY);
  return stored?.disabled === true
    && Number(stored?.protocol_session) === Number(protocolSession);
}

export function clearRepetitionPreference(storage = defaultStorage()) {
  try {
    storage?.removeItem?.(REPETITION_PREFERENCE_KEY);
  } catch {
    // A rejected removal leaves a stale waiver that isRepetitionDisabled still
    // validates against the current protocol session before honouring it.
  }
}


export function saveRepetitionPreference(
  disabled,
  protocolSession,
  storage = defaultStorage(),
) {
  if (!disabled || !canDisableRepetition(protocolSession)) {
    clearRepetitionPreference(storage);
    return false;
  }

  try {
    storage?.setItem?.(REPETITION_PREFERENCE_KEY, JSON.stringify({
      disabled: true,
      protocol_session: Number(protocolSession),
    }));
  } catch {
    return false;
  }
  return isRepetitionDisabled(storage, protocolSession);
}
