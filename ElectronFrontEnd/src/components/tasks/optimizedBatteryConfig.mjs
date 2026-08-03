import {
  ACTIVE_BATTERY_PROFILE,
  PROTOCOL_PROFILE_METADATA,
  PROTOCOL_PROFILE_REF,
  audioProfileForTask,
  profileComponentRefs,
  protocolProfileRefForTask,
  runnerProtocolFor,
  scoringRubricFor,
  scoringThresholdsFor,
  taskPresentationFor,
  taskTimingFor,
} from './optimizedBatteryProfile.mjs';

/**
 * Declarative contract for the optimized Mindspeller task battery.
 *
 * The bundled forms are deterministic research-candidate stimuli.  They make
 * the recorder runnable and auditable, but are deliberately not represented
 * as externally validated norms.  Every stored result includes the form and
 * protocol version so validated stimulus packs can replace these forms later
 * without changing canonical task identities.
 */

export const BATTERY_VERSION = `task_battery_optimization_${PROTOCOL_PROFILE_METADATA.profile_version}`;
export const STIMULUS_PACK_VERSION = PROTOCOL_PROFILE_METADATA.components.stimuli.version;
export const AUDIO_PACK_VERSION = PROTOCOL_PROFILE_METADATA.components.audio.version;
export const RUBRIC_SET_VERSION = PROTOCOL_PROFILE_METADATA.components.rubrics.version;
export const THRESHOLD_SET_VERSION = PROTOCOL_PROFILE_METADATA.components.thresholds.version;
export const PROTOCOL_VALIDATION_STATUS = PROTOCOL_PROFILE_METADATA.validation_status;
export const EYES_OPEN_BASELINE_CHECKPOINT = 'eyes_open_baseline';

export {
  ACTIVE_BATTERY_PROFILE,
  PROTOCOL_PROFILE_METADATA,
  PROTOCOL_PROFILE_REF,
  audioProfileForTask,
  profileComponentRefs,
  protocolProfileRefForTask,
  runnerProtocolFor,
  scoringRubricFor,
  scoringThresholdsFor,
  taskPresentationFor,
  taskTimingFor,
};

export const TASK_IDS = Object.freeze({
  NUMERICAL: 'adaptive_numerical_reasoning',
  WORKING_MEMORY: 'working_memory_manipulation',
  AUDITORY_COUNT: 'auditory_target_counting',
  SEMANTIC: 'semantic_induction_category_switching',
  VISUOSPATIAL: 'visuospatial_transformation_orientation',
  IDEATION: 'divergent_ideation',
  DUAL_TASK: 'dual_task_rule_switching',
  ANOMALY: 'rule_based_anomaly_detection',
  VISUAL_COMPARISON: 'rapid_visual_comparison',
  CLOSURE: 'pattern_closure_visual_noise',
  SPEECH_NOISE: 'speech_in_noise_comprehension',
  WRITTEN: 'written_comprehension_synthesis',
});

const phase = (id, label, start, end) => ({ id, label, start, end, duration: end - start });

const configuredTiming = (taskId) => {
  const timing = taskTimingFor(taskId);
  return {
    duration: timing.durationSeconds,
    phases: timing.phases.map((taskPhase) => phase(
      taskPhase.id,
      taskPhase.label,
      taskPhase.startSeconds,
      taskPhase.endSeconds,
    )),
  };
};

export const CLOSURE_REVEAL_SCHEDULE = Object.freeze({
  ...taskPresentationFor(TASK_IDS.CLOSURE),
});

export const TASK_DEFINITIONS = Object.freeze({
  [TASK_IDS.NUMERICAL]: {
    number: 1,
    name: 'Adaptive Numerical Reasoning and Sequencing',
    shortName: 'Numerical Reasoning',
    eyeState: 'closed',
    baseline: 'eyes_closed',
    ...configuredTiming(TASK_IDS.NUMERICAL),
    type: 'numerical',
    abilities: ['Mathematical Reasoning', 'Number Facility', 'Information Ordering', 'Deductive Reasoning'],
    blocked: ['Inductive Reasoning', 'Memorization', 'Reaction Time', 'Oral Comprehension', 'Oral Expression'],
    description: 'Listen to simple maths steps, one after another. Keep the answer in your head, and give it at the end.',
  },
  [TASK_IDS.WORKING_MEMORY]: {
    number: 2,
    name: 'Working-Memory Manipulation',
    shortName: 'Working Memory',
    eyeState: 'closed',
    baseline: 'eyes_closed',
    ...configuredTiming(TASK_IDS.WORKING_MEMORY),
    type: 'working_memory',
    abilities: ['Memorization', 'Information Ordering', 'Deductive Reasoning'],
    blocked: ['Inductive Reasoning', 'Category Flexibility', 'Time Sharing', 'Number Facility', 'Mathematical Reasoning', 'Oral Comprehension'],
    description: 'Listen to 4 numbers, then follow instructions that change their order. Give the final order at the end.',
  },
  [TASK_IDS.AUDITORY_COUNT]: {
    number: 3,
    name: 'Auditory Target Counting',
    shortName: 'Auditory Target Counting',
    eyeState: 'closed',
    baseline: 'eyes_closed',
    ...configuredTiming(TASK_IDS.AUDITORY_COUNT),
    type: 'auditory_count',
    abilities: ['Selective Attention', 'Auditory Attention'],
    blocked: ['Reaction Time', 'Speech Recognition', 'Oral Comprehension', 'Time Sharing', 'Problem Sensitivity'],
    description: 'Listen for beeps. Silently count the high tones. Ignore the low tones.',
  },
  [TASK_IDS.SEMANTIC]: {
    number: 4,
    name: 'Semantic Induction and Category Switching',
    shortName: 'Semantic Induction',
    eyeState: 'closed',
    baseline: 'eyes_closed',
    ...configuredTiming(TASK_IDS.SEMANTIC),
    type: 'semantic',
    abilities: ['Inductive Reasoning', 'Category Flexibility'],
    blocked: ['Deductive Reasoning', 'Memorization', 'Fluency of Ideas', 'Originality', 'Oral Comprehension'],
    description: 'Listen to a list of words and find out what connects them. Halfway through, the words change to a new category. Find that link too.',
  },
  [TASK_IDS.VISUOSPATIAL]: {
    number: 5,
    name: 'Visuospatial Transformation and Orientation',
    shortName: 'Visuospatial Tracking',
    eyeState: 'open',
    baseline: 'eyes_open',
    ...configuredTiming(TASK_IDS.VISUOSPATIAL),
    type: 'visuospatial',
    abilities: ['Visualization', 'Spatial Orientation'],
    blocked: ['Perceptual Speed', 'Speed of Closure', 'Flexibility of Closure', 'Reaction Time', 'Visual sensory abilities'],
    description: 'Watch an arrow on a grid. Each time it turns, follow where it moves and which way it points.',
  },
  [TASK_IDS.IDEATION]: {
    number: 6,
    name: 'Divergent Ideation',
    shortName: 'Divergent Ideation',
    eyeState: 'closed',
    baseline: 'eyes_closed',
    ...configuredTiming(TASK_IDS.IDEATION),
    type: 'ideation',
    abilities: ['Category Flexibility', 'Fluency of Ideas', 'Originality'],
    blocked: ['Written Expression', 'Oral Expression', 'Inductive Reasoning', 'Deductive Reasoning', 'Visualization'],
    description: 'Think of as many different uses for one object as you can. Do not write anything until the task ends.',
  },
  [TASK_IDS.DUAL_TASK]: {
    number: 7,
    name: 'Dual-Task Performance and Rule Switching',
    shortName: 'Dual Task & Switching',
    eyeState: 'closed',
    baseline: 'eyes_closed',
    ...configuredTiming(TASK_IDS.DUAL_TASK),
    type: 'dual_task',
    abilities: ['Time Sharing', 'Category Flexibility', 'Deductive Reasoning', 'Selective Attention', 'Information Ordering'],
    blocked: ['Mathematical Reasoning', 'Number Facility', 'Memorization', 'Reaction Time', 'Auditory Attention'],
    description: 'Do two things at once: count the high tones, and keep a running number that changes with each spoken update.',
  },
  [TASK_IDS.ANOMALY]: {
    number: 8,
    name: 'Rule-Based Anomaly Detection',
    shortName: 'Anomaly Detection',
    eyeState: 'open',
    baseline: 'eyes_open',
    ...configuredTiming(TASK_IDS.ANOMALY),
    type: 'anomaly',
    abilities: ['Problem Sensitivity', 'Deductive Reasoning', 'Selective Attention', 'Information Ordering'],
    blocked: ['Inductive Reasoning', 'Perceptual Speed', 'Reaction Time', 'Speed of Closure', 'Flexibility of Closure'],
    description: 'Watch a stream of codes. Each one should follow one simple rule. Silently count the number of codes that break that rule.',
  },
  [TASK_IDS.VISUAL_COMPARISON]: {
    number: 9,
    name: 'Rapid Visual Comparison',
    shortName: 'Rapid Visual Comparison',
    eyeState: 'open',
    baseline: 'eyes_open',
    ...configuredTiming(TASK_IDS.VISUAL_COMPARISON),
    type: 'visual_comparison',
    abilities: ['Perceptual Speed', 'Reaction Time'],
    blocked: ['Speed of Closure', 'Flexibility of Closure', 'Visualization', 'Spatial Orientation', 'Problem Sensitivity'],
    description: 'Watch two rows of letters and numbers. Press the button as soon as you notice a mismatch.',
  },
  [TASK_IDS.CLOSURE]: {
    number: 10,
    name: 'Pattern Closure under Visual Noise',
    shortName: 'Pattern Closure',
    eyeState: 'open',
    baseline: 'eyes_open',
    ...configuredTiming(TASK_IDS.CLOSURE),
    type: 'closure',
    abilities: ['Speed of Closure', 'Flexibility of Closure'],
    blocked: ['Perceptual Speed', 'Spatial Orientation', 'Problem Sensitivity', 'Reaction Time', 'Selective Attention'],
    description: 'Look at a fuzzy, noisy picture. It slowly becomes clearer. Press the button as soon as you know what it is.',
  },
  [TASK_IDS.SPEECH_NOISE]: {
    number: 11,
    name: 'Speech-in-Noise Comprehension',
    shortName: 'Speech in Noise',
    eyeState: 'closed',
    baseline: 'eyes_closed',
    ...configuredTiming(TASK_IDS.SPEECH_NOISE),
    type: 'speech_noise',
    abilities: ['Oral Comprehension', 'Speech Recognition', 'Auditory Attention'],
    blocked: ['Oral Expression', 'Speech Clarity', 'Reaction Time', 'Written Comprehension', 'Written Expression'],
    description: 'Listen to a short story, even though there is background noise. Answer some questions about it afterward.',
  },
  [TASK_IDS.WRITTEN]: {
    number: 12,
    name: 'Written Comprehension and Concise Synthesis',
    shortName: 'Written Comprehension',
    eyeState: 'open',
    baseline: 'eyes_open',
    ...configuredTiming(TASK_IDS.WRITTEN),
    type: 'written',
    abilities: ['Written Comprehension', 'Written Expression', 'Inductive Reasoning', 'Information Ordering'],
    blocked: ['Oral Comprehension', 'Oral Expression', 'Speech Recognition', 'Speech Clarity', 'Fluency of Ideas', 'Originality'],
    description: 'Read a short passage on the screen. Think about how to sum it up in your head, then write it after the task ends.',
  },
});

export function taskDefinitionForProfile(taskId, profile = ACTIVE_BATTERY_PROFILE) {
  const definition = TASK_DEFINITIONS[taskId];
  if (!definition) throw new Error(`No task definition configured for ${taskId}`);
  const timing = taskTimingFor(taskId, profile);
  return {
    ...definition,
    duration: timing.durationSeconds,
    phases: timing.phases.map((taskPhase) => phase(
      taskPhase.id,
      taskPhase.label,
      taskPhase.startSeconds,
      taskPhase.endSeconds,
    )),
  };
}

export const SESSION_SEQUENCES = Object.freeze({
  session_1: [
    TASK_IDS.AUDITORY_COUNT,
    TASK_IDS.WORKING_MEMORY,
    TASK_IDS.NUMERICAL,
    TASK_IDS.SEMANTIC,
  ],
  session_2: [
    TASK_IDS.AUDITORY_COUNT,
    TASK_IDS.WORKING_MEMORY,
    TASK_IDS.NUMERICAL,
    TASK_IDS.SEMANTIC,
    TASK_IDS.IDEATION,
    TASK_IDS.DUAL_TASK,
    EYES_OPEN_BASELINE_CHECKPOINT,
    TASK_IDS.VISUAL_COMPARISON,
    TASK_IDS.VISUOSPATIAL,
    TASK_IDS.ANOMALY,
  ],
  session_3: [
    TASK_IDS.AUDITORY_COUNT,
    TASK_IDS.WORKING_MEMORY,
    TASK_IDS.NUMERICAL,
    TASK_IDS.SEMANTIC,
    TASK_IDS.IDEATION,
    TASK_IDS.DUAL_TASK,
    TASK_IDS.SPEECH_NOISE,
    EYES_OPEN_BASELINE_CHECKPOINT,
    TASK_IDS.VISUAL_COMPARISON,
    TASK_IDS.VISUOSPATIAL,
    TASK_IDS.ANOMALY,
    TASK_IDS.CLOSURE,
    TASK_IDS.WRITTEN,
  ],
});

export function resolveSessionDepth(storage = globalThis.sessionStorage) {
  if (storage?.getItem?.('hasSessionThree') === 'true') return 'session_3';
  if (storage?.getItem?.('hasAdvancedBooking') === 'true') return 'session_2';
  return 'session_1';
}

export function taskSequenceForSession(sessionDepth) {
  return [...(SESSION_SEQUENCES[sessionDepth] || SESSION_SEQUENCES.session_1)];
}

export function taskIdsForSession(sessionDepth) {
  return taskSequenceForSession(sessionDepth).filter((id) => id !== EYES_OPEN_BASELINE_CHECKPOINT);
}

const FIRST_SESSION_BY_TASK = Object.freeze({
  [TASK_IDS.NUMERICAL]: 1,
  [TASK_IDS.WORKING_MEMORY]: 1,
  [TASK_IDS.AUDITORY_COUNT]: 1,
  [TASK_IDS.SEMANTIC]: 1,
  [TASK_IDS.VISUOSPATIAL]: 2,
  [TASK_IDS.IDEATION]: 2,
  [TASK_IDS.DUAL_TASK]: 2,
  [TASK_IDS.ANOMALY]: 2,
  [TASK_IDS.VISUAL_COMPARISON]: 2,
  [TASK_IDS.CLOSURE]: 3,
  [TASK_IDS.SPEECH_NOISE]: 3,
  [TASK_IDS.WRITTEN]: 3,
});

const sessionFormIndex = (taskId, sessionDepth) => {
  const sessionNumber = ({ session_1: 1, session_2: 2, session_3: 3 }[sessionDepth] ?? 1);
  return Math.max(0, sessionNumber - (FIRST_SESSION_BY_TASK[taskId] || 1));
};

const applyOperation = (value, operation) => {
  if (operation.op === 'add') return value + operation.value;
  if (operation.op === 'subtract') return value - operation.value;
  if (operation.op === 'multiply') return value * operation.value;
  if (operation.op === 'divide') return value / operation.value;
  return value;
};

const operationText = (operation) => ({
  add: `add ${operation.value}`,
  subtract: `subtract ${operation.value}`,
  multiply: `multiply by ${operation.value}`,
  divide: `divide by ${operation.value}`,
}[operation.op]);

function numericalForm(id, startValue, lower, higher) {
  const definition = TASK_DEFINITIONS[TASK_IDS.NUMERICAL];
  const presentation = taskPresentationFor(TASK_IDS.NUMERICAL);
  const finalStimulusAt = definition.duration - presentation.finalQuietSeconds;
  const higherStartAt = definition.phases[1].start;
  const lowerStartAt = presentation.firstStimulusSeconds;
  const lowerEndAt = higherStartAt - presentation.finalQuietSeconds;
  const lowerStep = lower.length > 1
    ? (lowerEndAt - lowerStartAt) / (lower.length - 1)
    : 0;
  const higherStep = higher.length > 1
    ? (finalStimulusAt - higherStartAt) / (higher.length - 1)
    : 0;
  const operations = [
    ...lower.map((operation, index) => ({ ...operation, at: lowerStartAt + index * lowerStep })),
    ...higher.map((operation, index) => ({ ...operation, at: higherStartAt + index * higherStep })),
  ];
  const answer = operations.reduce(applyOperation, startValue);
  return {
    id,
    startValue,
    operations,
    answer,
    spokenEvents: [
      { at: 0, text: `Start with ${startValue}.` },
      ...operations.map((operation) => ({ at: operation.at, text: operationText(operation) })),
    ],
  };
}

// Trimmed from 6 lower-load + 10 higher-load operations (the 90s original) to
// 4 + 7 for the 60s task. Counts were chosen, not just halved, so the interval
// between operations stays close to the original pace (~7.6s -> ~7.7s lower,
// ~4.7s -> ~4.5s higher) instead of everything getting rushed.
const NUMERICAL_FORMS = [
  numericalForm('num_a', 18,
    [{ op: 'add', value: 7 }, { op: 'multiply', value: 2 }, { op: 'subtract', value: 6 }, { op: 'add', value: 5 }],
    [{ op: 'add', value: 7 }, { op: 'divide', value: 2 }, { op: 'add', value: 13 }, { op: 'multiply', value: 2 }, { op: 'subtract', value: 11 }, { op: 'add', value: 5 }, { op: 'divide', value: 4 }]),
  numericalForm('num_b', 24,
    [{ op: 'subtract', value: 5 }, { op: 'add', value: 8 }, { op: 'multiply', value: 2 }, { op: 'subtract', value: 9 }],
    [{ op: 'divide', value: 2 }, { op: 'add', value: 15 }, { op: 'multiply', value: 2 }, { op: 'subtract', value: 18 }, { op: 'divide', value: 3 }, { op: 'add', value: 11 }, { op: 'multiply', value: 2 }]),
  numericalForm('num_c', 15,
    [{ op: 'add', value: 9 }, { op: 'multiply', value: 2 }, { op: 'subtract', value: 8 }, { op: 'add', value: 6 }],
    [{ op: 'multiply', value: 2 }, { op: 'subtract', value: 14 }, { op: 'divide', value: 3 }, { op: 'add', value: 16 }, { op: 'multiply', value: 2 }, { op: 'subtract', value: 20 }, { op: 'divide', value: 2 }]),
];

function applyMemoryCommand(sequence, command) {
  const next = [...sequence];
  if (command.op === 'reverse') return next.reverse();
  if (command.op === 'shift_left') return [...next.slice(1), next[0]];
  if (command.op === 'shift_right') return [next[next.length - 1], ...next.slice(0, -1)];
  if (command.op === 'replace') {
    next[command.index] = command.value;
    return next;
  }
  return next;
}

const memoryCommandText = (command) => {
  if (command.op === 'reverse') return 'Reverse the current order.';
  if (command.op === 'shift_left') return 'Shift every item one place to the left.';
  if (command.op === 'shift_right') return 'Shift every item one place to the right.';
  if (command.op === 'replace') return `Replace item ${command.index + 1} with ${command.value}.`;
  return 'Maintain the current sequence.';
};

function memoryForm(id, initial, commands) {
  const definition = TASK_DEFINITIONS[TASK_IDS.WORKING_MEMORY];
  const presentation = taskPresentationFor(TASK_IDS.WORKING_MEMORY);
  const phaseBoundary = definition.phases[1].start;
  const lowerCount = 2;
  const higherCount = commands.length - lowerCount;
  const finalUpdateAt = definition.duration - presentation.finalQuietSeconds;
  const scheduledCommands = commands.map((command, index) => {
    if (index < lowerCount) {
      const lowerSpan = phaseBoundary - presentation.firstUpdateSeconds - 10;
      return {
        ...command,
        at: presentation.firstUpdateSeconds + (lowerCount === 1 ? 0 : (index * lowerSpan) / (lowerCount - 1)),
      };
    }
    const higherIndex = index - lowerCount;
    return {
      ...command,
      at: phaseBoundary + (higherCount === 1 ? 0 : (higherIndex * (finalUpdateAt - phaseBoundary)) / (higherCount - 1)),
    };
  });
  const answer = scheduledCommands.reduce(applyMemoryCommand, initial);
  return {
    id,
    initial,
    commands: scheduledCommands,
    answer,
    spokenEvents: [
      { at: 0, text: `Remember this sequence: ${initial.join(', ')}.` },
      ...scheduledCommands.map((command) => ({ at: command.at, text: memoryCommandText(command) })),
    ],
  };
}

const MEMORY_FORMS = [
  memoryForm('wm_a', [4, 7, 2, 5], [
    { at: 8, op: 'maintain' }, { at: 18, op: 'shift_left' },
    { at: 25, op: 'reverse' }, { at: 32, op: 'replace', index: 1, value: 9 },
    { at: 37, op: 'shift_right' }, { at: 42, op: 'reverse' },
    { at: 47, op: 'replace', index: 3, value: 6 }, { at: 52, op: 'shift_left' },
  ]),
  memoryForm('wm_b', [6, 1, 8, 3], [
    { at: 8, op: 'maintain' }, { at: 18, op: 'shift_right' },
    { at: 25, op: 'replace', index: 2, value: 4 }, { at: 32, op: 'reverse' },
    { at: 37, op: 'shift_left' }, { at: 42, op: 'replace', index: 0, value: 7 },
    { at: 47, op: 'reverse' }, { at: 52, op: 'shift_right' },
  ]),
  memoryForm('wm_c', [9, 2, 5, 7], [
    { at: 8, op: 'maintain' }, { at: 18, op: 'replace', index: 1, value: 6 },
    { at: 25, op: 'shift_left' }, { at: 32, op: 'reverse' },
    { at: 37, op: 'replace', index: 3, value: 1 }, { at: 42, op: 'shift_right' },
    { at: 47, op: 'reverse' }, { at: 52, op: 'shift_left' },
  ]),
];

function seededUnit(seed) {
  let state = seed >>> 0;
  return () => {
    state = (1664525 * state + 1013904223) >>> 0;
    return state / 4294967296;
  };
}

function toneForm(
  id,
  seed,
  toneCount,
  targetCount,
  duration = TASK_DEFINITIONS[TASK_IDS.AUDITORY_COUNT].duration,
) {
  const presentation = taskPresentationFor(TASK_IDS.AUDITORY_COUNT);
  const audio = audioProfileForTask(TASK_IDS.AUDITORY_COUNT);
  const random = seededUnit(seed);
  const targetIndexes = new Set();
  while (targetIndexes.size < targetCount) {
    targetIndexes.add(Math.floor(random() * toneCount));
  }
  const rawIntervals = Array.from({ length: toneCount }, () => 0.68 + random() * 0.34);
  const availableIntervalSeconds = duration
    - presentation.firstToneSeconds
    - presentation.finalQuietSeconds;
  const scale = availableIntervalSeconds / rawIntervals.reduce((sum, value) => sum + value, 0);
  let at = presentation.firstToneSeconds;
  const toneEvents = rawIntervals.map((interval, index) => {
    at += interval * scale;
    const target = targetIndexes.has(index);
    return {
      at,
      target,
      frequency: target ? audio.targetFrequencyHz : audio.distractorFrequencyHz,
      durationMs: audio.durationMs,
      audioProfileId: PROTOCOL_PROFILE_METADATA.components.audio.id,
    };
  });
  return { id, toneEvents, targetCount };
}

const AUDITORY_FORMS = [
  toneForm('tones_a', 3101, 70, 16),
  toneForm('tones_b', 3102, 68, 15),
  toneForm('tones_c', 3103, 72, 17),
];

const SEMANTIC_FORMS = [
  {
    id: 'semantic_a',
    ruleOne: 'tools',
    ruleTwo: 'materials and their properties',
    phaseOne: ['hammer', 'saw', 'drill', 'wrench', 'pliers', 'chisel', 'level', 'clamp', 'file', 'mallet', 'tape measure', 'plane', 'vice', 'crowbar', 'screwdriver'],
    phaseTwo: ['steel, strong', 'rubber, elastic', 'glass, brittle', 'copper, conductive', 'wool, insulating', 'silk, smooth', 'granite, hard', 'foam, light', 'clay, mouldable', 'wax, soft', 'wood, rigid', 'paper, absorbent', 'plastic, flexible', 'ceramic, heat resistant', 'cotton, breathable'],
    ruleOptions: ['tools', 'animals and habitats', 'professions and workplaces', 'vehicles'],
    secondRuleOptions: ['materials and their properties', 'foods and flavours', 'vehicles and energy sources', 'countries and capitals'],
  },
  {
    id: 'semantic_b',
    ruleOne: 'animals and habitats',
    ruleTwo: 'foods and flavours',
    phaseOne: ['camel, desert', 'otter, river', 'eagle, mountain', 'frog, pond', 'seal, coast', 'mole, underground', 'monkey, forest', 'yak, plateau', 'penguin, ice', 'beaver, stream', 'owl, woodland', 'crab, shore', 'lizard, rock', 'heron, wetland', 'fox, meadow'],
    phaseTwo: ['lemon, sour', 'honey, sweet', 'coffee, bitter', 'chilli, hot', 'olive, savoury', 'mint, fresh', 'cocoa, rich', 'lime, sharp', 'vanilla, mild', 'ginger, spicy', 'salt, salty', 'apple, crisp', 'cream, smooth', 'grapefruit, tart', 'caramel, sweet'],
    ruleOptions: ['animals and habitats', 'tools', 'professions and workplaces', 'shapes and colours'],
    secondRuleOptions: ['foods and flavours', 'materials and their properties', 'vehicles and energy sources', 'countries and capitals'],
  },
  {
    id: 'semantic_c',
    ruleOne: 'professions and workplaces',
    ruleTwo: 'vehicles and energy sources',
    phaseOne: ['chef, kitchen', 'teacher, classroom', 'nurse, clinic', 'pilot, cockpit', 'judge, courtroom', 'farmer, field', 'scientist, laboratory', 'actor, theatre', 'librarian, library', 'mechanic, garage', 'architect, studio', 'firefighter, station', 'baker, bakery', 'dentist, surgery', 'reporter, newsroom'],
    phaseTwo: ['tram, electricity', 'bicycle, muscle', 'bus, diesel', 'sailboat, wind', 'car, petrol', 'train, electricity', 'glider, gravity', 'scooter, battery', 'ferry, diesel', 'rocket, fuel', 'canoe, muscle', 'trolleybus, electricity', 'hot-air balloon, heat', 'submarine, nuclear power', 'skateboard, muscle'],
    ruleOptions: ['professions and workplaces', 'tools', 'animals and habitats', 'foods'],
    secondRuleOptions: ['vehicles and energy sources', 'foods and flavours', 'materials and their properties', 'countries and capitals'],
  },
].map((form) => {
  const [ruleOnePhase, ruleTwoPhase] = TASK_DEFINITIONS[TASK_IDS.SEMANTIC].phases;
  return {
    ...form,
    spokenEvents: [
      ...form.phaseOne.map((text, index) => ({
        at: ruleOnePhase.start + (index * ruleOnePhase.duration) / form.phaseOne.length,
        text,
      })),
      ...form.phaseTwo.map((text, index) => ({
        at: ruleTwoPhase.start + (index * ruleTwoPhase.duration) / form.phaseTwo.length,
        text,
      })),
    ],
  };
});

const ORIENTATIONS = ['north', 'east', 'south', 'west'];

function routeStateAt(form, elapsedSeconds) {
  let x = form.start.x;
  let y = form.start.y;
  let orientationIndex = ORIENTATIONS.indexOf(form.start.orientation);
  let applied = 0;
  for (const move of form.moves) {
    if (move.at > elapsedSeconds) break;
    orientationIndex = (orientationIndex + (move.turn === 'right' ? 1 : 3)) % 4;
    if (orientationIndex === 0) y -= 1;
    if (orientationIndex === 1) x += 1;
    if (orientationIndex === 2) y += 1;
    if (orientationIndex === 3) x -= 1;
    applied += 1;
  }
  return { x, y, orientation: ORIENTATIONS[orientationIndex], applied };
}

function routeForm(id, start, moves) {
  const definition = TASK_DEFINITIONS[TASK_IDS.VISUOSPATIAL];
  const presentation = taskPresentationFor(TASK_IDS.VISUOSPATIAL);
  const phaseBoundary = definition.phases[1].start;
  const lowerMoves = moves.slice(0, 4);
  const higherMoves = moves.slice(4);
  const scheduledMoves = [
    ...lowerMoves.map((move, index) => ({
      ...move,
      at: 8 + (index * (phaseBoundary - 12)) / Math.max(1, lowerMoves.length - 1),
    })),
    ...higherMoves.map((move, index) => ({
      ...move,
      at: phaseBoundary + (
        index * (definition.duration - presentation.finalQuietSeconds - phaseBoundary)
      ) / Math.max(1, higherMoves.length - 1),
    })),
  ];
  const form = { id, start, moves: scheduledMoves };
  let previous = { ...start };
  for (const move of scheduledMoves) {
    const next = routeStateAt(form, move.at);
    const inBounds = next.x >= 0 && next.x <= 4 && next.y >= 0 && next.y <= 4;
    const positionChanged = next.x !== previous.x || next.y !== previous.y;
    const orientationChanged = next.orientation !== previous.orientation;
    if (!inBounds || !positionChanged || !orientationChanged) {
      throw new Error(`Invalid route step in ${id} at ${move.at}s`);
    }
    previous = next;
  }
  return { ...form, answer: routeStateAt(form, Number.POSITIVE_INFINITY) };
}

const ROUTE_FORMS = [
  routeForm('route_a', { x: 2, y: 2, orientation: 'north' }, [
    { at: 5, turn: 'right' }, { at: 11, turn: 'right' }, { at: 17, turn: 'right' }, { at: 23, turn: 'right' },
    { at: 25, turn: 'left' }, { at: 30, turn: 'right' }, { at: 34, turn: 'right' }, { at: 38, turn: 'left' }, { at: 42, turn: 'left' }, { at: 46, turn: 'left' }, { at: 50, turn: 'right' },
  ]),
  routeForm('route_b', { x: 1, y: 3, orientation: 'east' }, [
    { at: 5, turn: 'right' }, { at: 11, turn: 'left' }, { at: 17, turn: 'left' }, { at: 23, turn: 'right' },
    { at: 25, turn: 'right' }, { at: 30, turn: 'left' }, { at: 34, turn: 'left' }, { at: 38, turn: 'left' }, { at: 42, turn: 'right' }, { at: 46, turn: 'left' }, { at: 50, turn: 'right' },
  ]),
  routeForm('route_c', { x: 3, y: 2, orientation: 'south' }, [
    { at: 5, turn: 'left' }, { at: 11, turn: 'right' }, { at: 17, turn: 'right' }, { at: 23, turn: 'left' },
    { at: 25, turn: 'left' }, { at: 30, turn: 'left' }, { at: 34, turn: 'left' }, { at: 38, turn: 'right' }, { at: 42, turn: 'right' }, { at: 46, turn: 'right' }, { at: 50, turn: 'right' },
  ]),
];

function ideationForm(id, prompt) {
  return { id, prompt, spokenEvents: [{ at: 0, text: prompt }] };
}

const IDEATION_FORMS = [
  ideationForm('ideas_a', 'A brick.'),
  ideationForm('ideas_b', 'A paper cup.'),
  ideationForm('ideas_c', 'A shoelace.'),
];

function dualTaskForm(id, seed, toneCount, targetCount, startValue, beforeDelta, afterDelta) {
  const definition = TASK_DEFINITIONS[TASK_IDS.DUAL_TASK];
  const switchAt = definition.phases[1].start;
  const tones = toneForm(`${id}_tones`, seed, toneCount, targetCount, definition.duration);
  // Few, widely spaced updates (~20 s apart, with a clear gap around the switch
  // cue) keep the running total easy and unhurried.
  const beforeUpdateTimes = [14, 34, 52];
  const afterUpdateTimes = [74, 94, 112];
  const updateTimes = [...beforeUpdateTimes, ...afterUpdateTimes];
  const finalValue = updateTimes.reduce(
    (value, at) => value + (at < switchAt ? beforeDelta : afterDelta),
    startValue,
  );
  return {
    ...tones,
    id,
    startValue,
    beforeDelta,
    afterDelta,
    updateTimes,
    finalValue,
    spokenEvents: [
      { at: 0, text: `Start with ${startValue}.` },
      ...updateTimes.map((at) => ({ at, text: 'Update.' })),
      { at: switchAt, text: 'Switch.' },
    ],
  };
}

// Eased dual task: keep the tone stream (Selective Attention) and the single
// rule switch (Category Flexibility), but make the number task a light,
// addition-only running total. This preserves the report's ability set
// (Time Sharing, Deductive Reasoning, Information Ordering) without the mental
// arithmetic the report excludes (Mathematical Reasoning, Number Facility).
// Fewer target tones (10) further lighten the concurrent count.
const DUAL_FORMS = [
  dualTaskForm('dual_a', 7101, 70, 10, 0, 1, 2),
  dualTaskForm('dual_b', 7102, 68, 10, 4, 2, 1),
  dualTaskForm('dual_c', 7103, 72, 10, 10, 1, 2),
];

const VALID_CODES = ['A-47', 'B-18', 'C-62', 'D-05', 'E-91', 'F-33', 'G-74', 'H-26', 'J-80', 'K-14', 'L-59', 'M-42', 'N-07', 'P-68', 'Q-31', 'R-95', 'S-24', 'T-76', 'U-11', 'V-53', 'W-89', 'X-36', 'Y-20', 'Z-64'];
const ANOMALIES = [
  { value: 'AB-7', type: 'extra_letter' },
  { value: '4-C7', type: 'wrong_order' },
  { value: 'D47', type: 'missing_separator' },
  { value: 'E-9', type: 'missing_digit' },
  { value: 'F_23', type: 'wrong_separator' },
  { value: '73-G', type: 'wrong_order' },
];

function anomalyForm(id, offset) {
  const presentation = taskPresentationFor(TASK_IDS.ANOMALY);
  const duration = TASK_DEFINITIONS[TASK_IDS.ANOMALY].duration;
  const entryCount = Math.ceil(duration / presentation.entryIntervalSeconds);
  const lowerAnomalySlots = [8, 16, 22];
  const higherAnomalySlots = [25, 29, 33, 37, 41, 44];
  const anomalySlots = [...lowerAnomalySlots, ...higherAnomalySlots]
    .filter((index) => index < entryCount);
  const entries = [];
  let validIndex = offset;
  for (let index = 0; index < entryCount; index += 1) {
    const anomalyPosition = anomalySlots.indexOf(index);
    if (anomalyPosition >= 0) entries.push(ANOMALIES[(anomalyPosition + offset) % ANOMALIES.length]);
    else {
      entries.push({ value: VALID_CODES[validIndex % VALID_CODES.length], type: null });
      validIndex += 1;
    }
  }
  const anomalyTypes = [...new Set(entries.filter((entry) => entry.type).map((entry) => entry.type))];
  return {
    id,
    rule: 'A correct code has 1 letter, then a hyphen, then 2 digits, in that same order. For example: A-47.',
    entries,
    entryIntervalSeconds: presentation.entryIntervalSeconds,
    anomalyCount: anomalySlots.length,
    anomalyTypes,
  };
}

const ANOMALY_FORMS = [anomalyForm('anomaly_a', 0), anomalyForm('anomaly_b', 2), anomalyForm('anomaly_c', 4)];

const VISUAL_CODE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';

function comparisonCode(random) {
  const groups = Array.from({ length: 3 }, () => (
    Array.from({ length: 4 }, () => (
      VISUAL_CODE_ALPHABET[Math.floor(random() * VISUAL_CODE_ALPHABET.length)]
    )).join('')
  ));
  return groups.join('-');
}

function comparisonReplacement(character, offset) {
  const index = VISUAL_CODE_ALPHABET.indexOf(character);
  if (index < 0) throw new Error(`Cannot replace non-code character ${character}`);
  return VISUAL_CODE_ALPHABET[(index + offset) % VISUAL_CODE_ALPHABET.length];
}

// After the first mismatched position appears at mismatchOnset, one more
// position joins it every MISMATCH_ESCALATION_STEP_FRAMES code refreshes, so
// the two rows keep diverging further for anyone who missed the first, subtle
// difference, instead of staying at a single changed character for the rest
// of the block. Escalating on a frame count rather than a raw time interval
// means each newly added mismatch is already present the instant the row
// updates to its next code, rather than popping up mid-display on an
// otherwise-unchanged pair.
const MISMATCH_ESCALATION_STEP_FRAMES = 2;

function visualComparisonForm(id, seed, mismatchOnset, mismatchIndices, replacementOffset) {
  const presentation = taskPresentationFor(TASK_IDS.VISUAL_COMPARISON);
  const updateIntervalSeconds = presentation.updateIntervalSeconds;
  const frameCount = Math.ceil(
    TASK_DEFINITIONS[TASK_IDS.VISUAL_COMPARISON].duration / updateIntervalSeconds,
  ) + 1;
  const random = seededUnit(seed);
  const frames = Array.from({ length: frameCount }, () => comparisonCode(random));
  if (frames.some((code) => mismatchIndices.some((index) => code[index] === '-'))) {
    throw new Error(`${id} mismatch positions must contain a code character in every frame`);
  }
  return {
    id,
    frames,
    updateIntervalSeconds,
    mismatchIndices,
    replacementOffset,
    mismatchOnset,
  };
}

// Every mismatchOnset below is a multiple of updateIntervalSeconds (3s) so the
// very first mismatch, like every escalation step after it, is already
// present the instant the row refreshes rather than appearing mid-display.
const VISUAL_COMPARISON_FORMS = [
  visualComparisonForm('compare_a', 9101, 27, [11, 2, 7, 0, 13], 5),
  visualComparisonForm('compare_b', 9102, 27, [6, 1, 10, 3, 12], 7),
  visualComparisonForm('compare_c', 9103, 24, [13, 0, 7, 10, 2], 9),
];

const closureForm = (id, target, symbol, options) => ({
  id,
  target,
  symbol,
  options,
  revealSchedule: CLOSURE_REVEAL_SCHEDULE,
});

const CLOSURE_FORMS = [
  closureForm('closure_a', 'umbrella', '☂', ['umbrella', 'mushroom', 'lamp', 'tree']),
  closureForm('closure_b', 'sailboat', '⛵', ['sailboat', 'mountain', 'chair', 'bird']),
  closureForm('closure_c', 'key', '⚿', ['key', 'spoon', 'pencil', 'fish']),
];

const SPEECH_BASE_FORMS = [
  {
    id: 'speech_a',
    // Simplified to short, plain sentences (same intent as Task 12's
    // passages) so a listener with weak reading/language skills can still
    // follow it by ear.
    passage: 'A town by the coast used to flood every winter. The town did not build one huge wall to stop the water. Instead, workers rebuilt the sand dunes, made a marsh bigger, and raised the lowest paths. The next big storm still brought high water. But the marsh slowed the wave, and the dunes kept the water away from homes. Engineers said no single fix could remove all danger. So the town also built clear escape routes and ran regular warning tests. The plan worked because nature, planning, and ready people all helped each other. It also gave new homes to animals and made the coast nicer to visit on calm days.',
    continuation: 'Before the work started, workers checked where water came into the streets. They also found which older people would need help leaving their homes. People practiced the escape routes on a dry day. This is how they found out that one bridge was too narrow for trucks. So the plan was fixed before the next storm season. Local shops agreed to keep flood barriers ready. Schools taught children what to do if a flood came. After each storm, workers checked the marsh and the dunes and fixed the parts that wore away the most.',
    mainIdea: 'Many different steps together lowered the flood risk.',
    mainIdeaOptions: ['One giant wall stopped every future flood.', 'Many different steps together lowered the flood risk.', 'The town stopped caring for the coast once the project ended.'],
    keyDetailQuestion: 'What slowed the wave?',
    keyDetail: 'the marsh',
    // Every distractor is a flood defence the passage actually describes, so
    // the item cannot be solved by picking the most sensible-sounding answer —
    // only by recalling which one the passage credited with slowing the wave.
    keyDetailOptions: ['the sand dunes', 'the marsh', 'the raised paths', 'the flood barriers'],
  },
  {
    id: 'speech_b',
    // Simplified (see speech_a's comment).
    passage: 'A hospital saw that medicine often arrived late. This happened even though every team worked fast. A review found that each team used different names for the same things. So staff kept stopping to check different labels. The hospital gave everyone one shared code instead. It also moved common supplies closer to the patient rooms. Short handover checks were added too. Delivery got faster, and nobody had to rush. The real problem was not effort. It was how things were organized and laid out. Leaders still kept a paper backup plan, in case the computer system failed. After three months, mistakes dropped and nurses had more time with patients.',
    continuation: 'The review team followed medicine orders from the pharmacy all the way to the patient bed. They found many small mix-ups added up over time. One storage room used a short name for a ward. A cart was restocked at random times. Urgent orders waited in the same line as normal orders. Workers from many teams designed the fix together. They tested the new shared code on one floor first. They checked if the labels were easy to read in different light. If a code looked too much like another one, they changed it. The hospital also made it clear who should fix each kind of problem.',
    mainIdea: 'Shared systems and better layout made medicine delivery faster.',
    mainIdeaOptions: ['Nurses were told to walk and work faster.', 'The hospital got rid of every backup plan.', 'Shared systems and better layout made medicine delivery faster.'],
    keyDetailQuestion: 'Why did staff keep stopping?',
    keyDetail: 'to check different labels',
    // Each distractor is a delay the passage genuinely names (the randomly
    // restocked cart, supplies that were far from the wards, urgent orders
    // queued with routine ones), so all four read as credible causes.
    keyDetailOptions: ['to wait for the restocking cart', 'to walk to distant storage rooms', 'to check different labels', 'to let urgent orders pass first'],
  },
  {
    id: 'speech_c',
    // Simplified (see speech_a's comment).
    passage: 'A school library wanted more students to use its science books. Buying more books had not helped much. So the librarian tried something new. Small displays connected science topics to class projects. Teachers got short guides showing where to find good material. Students could also leave questions on a board for the next class to answer. More books got borrowed. But the biggest change was that students started talking about their sources and comparing ideas. The library kept changing the displays so they matched what each class was learning. Things improved because information was easy to see, came at the right time, and had a clear purpose.',
    continuation: 'At first, the displays covered a space project and a water quality project. Each display had books at different reading levels, a picture, a short article, and a question with more than one possible source. Teachers brought their class to the display before starting research. This helped students see how the books connected to a question they already understood. The librarian tracked which books were borrowed. She also tracked which questions appeared on the board and which sources students used to answer them. If a display got little attention, its position or label was changed. Students helped pick new topics for later displays too.',
    mainIdea: 'Connecting visible materials to class projects made the library more useful.',
    mainIdeaOptions: ['The library only succeeded by buying many new books.', 'Connecting visible materials to class projects made the library more useful.', 'The displays never changed once they were set up.'],
    keyDetailQuestion: 'Where could students leave questions?',
    keyDetail: 'on a board',
    // The displays and the librarian are both central to the passage, and a
    // question box is the answer a listener would expect from a school library
    // without having heard this one, so no option is dismissible on sight.
    keyDetailOptions: ['at the display', 'with the librarian', 'in a question box', 'on a board'],
  },
];

const SPEECH_FORMS = SPEECH_BASE_FORMS.map(({ continuation, ...form }) => {
  const audioProfile = audioProfileForTask(TASK_IDS.SPEECH_NOISE);
  return {
    ...form,
    passage: `${form.passage} ${continuation}`,
    nominalSnrDb: audioProfile.nominalSnrDb,
    audioProfile,
  };
});

const WRITTEN_BASE_FORMS = [
  {
    id: 'written_a',
    // Simplified to short, plain sentences (see tools/README.md-style intent:
    // easy enough for a low-literacy reader) while keeping the same topic and
    // main idea as before.
    passage: 'Cities get very hot in summer. Many people turn on air conditioners to stay cool. But a city can also cool itself in other ways. Trees give shade to walls and streets. Plants and soil hold water and slowly release it into the air, which cools things down. Light-colored roofs stay cooler than dark roofs, because they reflect more sunlight. One roof only cools one building. But many trees together can cool a whole street and the homes near it. These ideas do not work on their own. New trees take years to grow big enough to give real shade. Shiny roofs can create annoying glare if they are placed the wrong way. Water for new plants can also be hard to find. Because of this, a good city plan needs more than one idea. It needs local weather facts, money for care, and input from the people who live there. No single fix solves the whole problem by itself. Cities also need cooling centers for very hot days. These help people whose homes cannot be fixed quickly.',
    mainIdea: 'Cities cool down best when several ideas work together, not just one.',
    mainIdeaOptions: ['Air conditioners are the only way to cool a city.', 'Planting trees fixes city heat right away and needs no care.', 'Cities cool down best when several ideas work together, not just one.'],
  },
  {
    id: 'written_b',
    // Simplified (see written_a's comment).
    passage: 'Some people think more numbers always lead to better choices. But too many numbers can make a decision harder, not easier. This happens when nobody agrees on what each number should tell you to do. A good chart should start with the choice you need to make, not with the data. First, decide who makes the choice and how often. Then decide what result should make them act. After that, pick only a few numbers that show that result clearly. The numbers still need context. A sudden change might just be a mistake in how the data was collected, not a real change. Because of this, good charts explain what each number means and who is in charge of it. They also let people check the original data if something looks wrong. Being simple does not mean hiding problems. It means showing the important facts clearly and removing anything that is not needed. Old numbers that nobody uses anymore should be removed. A good chart helps people go from information to a smart choice quickly. It is not about having the most numbers possible.',
    mainIdea: 'Good charts use a few clear numbers that are picked to help people decide.',
    mainIdeaOptions: ['The best chart always shows as many numbers as possible.', 'Good charts use a few clear numbers that are picked to help people decide.', 'Charts should hide problems so users do not get confused.'],
  },
  {
    id: 'written_c',
    // Simplified (see written_a's comment).
    passage: 'Fixing broken things can save money and materials. But whether a thing can be fixed depends on choices made before it ever breaks. A product is easy to fix if its screws can be opened. It also helps if broken parts can be swapped out and repair guides are easy to find. Even a fixable product might still get thrown away, if new parts take too long to arrive or cost almost as much as a new item. New rules can help by making manuals and spare parts easier to find. Companies can also design products so parts can be swapped later, which makes the product last longer. People who fix their own things need good instructions too, because a bad repair can be unsafe. Fixing things is not just one shop’s job. Designers, sellers, repair shops, lawmakers, and users all play a part. Just counting repairs is not enough. Strong, well-made products need less repair in the first place, and simple care can stop many problems before they start. The best plan combines strong design, regular care, repair, reuse, and safe recycling. Each choice should depend on safety, cost, and how worn the item is.',
    mainIdea: 'Whether something can be fixed depends on many people working together, not just repair shops.',
    mainIdeaOptions: ['Every broken item should always be repaired, no matter the cost or danger.', 'Only repair shops decide whether something can be fixed.', 'Whether something can be fixed depends on many people working together, not just repair shops.'],
  },
];

const WRITTEN_FORMS = WRITTEN_BASE_FORMS.map((form) => ({
  ...form,
  ...taskPresentationFor(TASK_IDS.WRITTEN),
}));

const FORMS_BY_TASK = {
  [TASK_IDS.NUMERICAL]: NUMERICAL_FORMS,
  [TASK_IDS.WORKING_MEMORY]: MEMORY_FORMS,
  [TASK_IDS.AUDITORY_COUNT]: AUDITORY_FORMS,
  [TASK_IDS.SEMANTIC]: SEMANTIC_FORMS,
  [TASK_IDS.VISUOSPATIAL]: ROUTE_FORMS,
  [TASK_IDS.IDEATION]: IDEATION_FORMS,
  [TASK_IDS.DUAL_TASK]: DUAL_FORMS,
  [TASK_IDS.ANOMALY]: ANOMALY_FORMS,
  [TASK_IDS.VISUAL_COMPARISON]: VISUAL_COMPARISON_FORMS,
  [TASK_IDS.CLOSURE]: CLOSURE_FORMS,
  [TASK_IDS.SPEECH_NOISE]: SPEECH_FORMS,
  [TASK_IDS.WRITTEN]: WRITTEN_FORMS,
};

export const CANDIDATE_PILOT_STIMULUS_PACK = Object.freeze({
  ...PROTOCOL_PROFILE_METADATA.components.stimuli,
  language: ACTIVE_BATTERY_PROFILE.language,
  formsByTask: Object.freeze(FORMS_BY_TASK),
});

export const STIMULUS_PACK_REGISTRY = Object.freeze({
  [CANDIDATE_PILOT_STIMULUS_PACK.version]: CANDIDATE_PILOT_STIMULUS_PACK,
});

export const ACTIVE_STIMULUS_PACK = STIMULUS_PACK_REGISTRY[STIMULUS_PACK_VERSION];

export function taskFormForSession(taskId, sessionDepth, stimulusPack = ACTIVE_STIMULUS_PACK) {
  const forms = stimulusPack?.formsByTask?.[taskId];
  if (!forms?.length) throw new Error(`No stimulus form configured for ${taskId}`);
  return forms[Math.min(sessionFormIndex(taskId, sessionDepth), forms.length - 1)];
}

export function visualRouteState(form, elapsedSeconds) {
  return routeStateAt(form, elapsedSeconds);
}

export function closureRevealState(form, elapsedSeconds) {
  const schedule = form?.revealSchedule || CLOSURE_REVEAL_SCHEDULE;
  const elapsed = Number.isFinite(Number(elapsedSeconds)) ? Math.max(0, Number(elapsedSeconds)) : 0;
  const revealDuration = Math.max(0.001, schedule.fullyVisibleSeconds - schedule.revealStartSeconds);
  const revealFraction = Math.max(0, Math.min(1, (elapsed - schedule.revealStartSeconds) / revealDuration));
  return {
    revealFraction,
    fragmentProgress: Math.min(1, 0.06 + revealFraction * 0.94),
    symbolOpacity: Math.min(1, 0.18 + revealFraction * 0.82),
    blurPx: schedule.maximumBlurPx * (1 - revealFraction),
    noiseOpacity: schedule.minimumNoiseOpacity
      + (1 - revealFraction) * (schedule.initialNoiseOpacity - schedule.minimumNoiseOpacity),
    responseEnabled: elapsed >= schedule.responseEnabledSeconds,
  };
}

export function visualComparisonFrame(form, elapsedSeconds) {
  const frames = Array.isArray(form?.frames) ? form.frames : [];
  if (!frames.length) return { base: '', changed: '', mismatchIndices: [] };
  const elapsed = Number.isFinite(Number(elapsedSeconds)) ? Math.max(0, Number(elapsedSeconds)) : 0;
  const interval = Math.max(0.1, Number(form.updateIntervalSeconds) || 1);
  const frameIndex = Math.min(frames.length - 1, Math.floor(elapsed / interval));
  const base = frames[frameIndex];
  const allIndices = Array.isArray(form.mismatchIndices) ? form.mismatchIndices : [];
  const onsetFrameIndex = Math.floor(form.mismatchOnset / interval);
  const activeCount = elapsed < form.mismatchOnset
    ? 0
    : Math.min(
      allIndices.length,
      1 + Math.floor((frameIndex - onsetFrameIndex) / MISMATCH_ESCALATION_STEP_FRAMES),
    );
  const mismatchIndices = allIndices.slice(0, activeCount);
  const characters = [...base];
  for (const index of mismatchIndices) {
    characters[index] = comparisonReplacement(characters[index], form.replacementOffset);
  }
  return {
    base,
    changed: characters.join(''),
    mismatchIndices,
    frameIndex,
  };
}

function splitIntoSentences(text) {
  const matches = String(text ?? '').match(/[^.!?]+[.!?]+(?:\s+|$)/g);
  if (matches) return matches.map((sentence) => sentence.trim()).filter(Boolean);
  const trimmed = String(text ?? '').trim();
  return trimmed ? [trimmed] : [];
}

// Groups the passage's sentences into `chunkCount` reading-pane chunks, each a
// whole number of complete sentences (never a mid-sentence split), while
// keeping each chunk's word count close to its even share of the passage.
function sentenceChunks(passage, chunkCount) {
  const sentences = splitIntoSentences(passage);
  const wordCounts = sentences.map((sentence) => countWords(sentence));
  const totalWords = wordCounts.reduce((sum, count) => sum + count, 0);

  const chunks = Array.from({ length: chunkCount }, () => []);
  let chunkIndex = 0;
  let cumulativeWords = 0;
  for (let index = 0; index < sentences.length; index += 1) {
    chunks[chunkIndex].push(sentences[index]);
    cumulativeWords += wordCounts[index];

    const remainingChunks = chunkCount - chunkIndex - 1;
    const remainingSentences = sentences.length - index - 1;
    // Compare against each chunk boundary's cumulative share of the whole
    // passage, not a per-chunk total that resets every time — otherwise later
    // targets keep growing while the running count restarts at zero and can
    // never catch up, starving the final chunks.
    const reachedShare = cumulativeWords >= (totalWords * (chunkIndex + 1)) / chunkCount;
    // Never close a chunk if doing so would leave fewer sentences than chunks
    // still needing at least one.
    const canSpareASentence = remainingSentences >= remainingChunks;
    if (remainingChunks > 0 && reachedShare && canSpareASentence) {
      chunkIndex += 1;
    }
  }
  return chunks.map((group) => group.join(' '));
}

export function pacedPassageChunk(form, elapsedSeconds, options = {}) {
  const presentation = taskPresentationFor(TASK_IDS.WRITTEN);
  const readingDuration = Number(options.readingDurationSeconds)
    || Number(form?.readingDurationSeconds)
    || presentation.readingDurationSeconds;
  const chunkCount = Number(options.chunkCount)
    || Number(form?.chunkCount)
    || presentation.chunkCount;
  const chunkIndex = Math.min(chunkCount - 1, Math.floor((elapsedSeconds / readingDuration) * chunkCount));
  return sentenceChunks(form?.passage, chunkCount)[chunkIndex] || '';
}

export function taskIntroduction(taskId, form) {
  const definition = TASK_DEFINITIONS[taskId];
  const common = [
    `This task takes ${definition.duration} seconds. Do not stop until it is finished.`,
    `Keep your eyes ${definition.eyeState} the whole time. Try not to blink, clench your jaw, or move.`,
    'Wait to speak, write or type. You can give your answer after this task ends.',
  ];
  const specificFactory = {
    [TASK_IDS.NUMERICAL]: () => [
      `You will start with the number ${form.startValue}.`,
      'Then you will hear steps like "add 7" or "subtract 6". Do the maths in your head after each one.',
      'Give only your final answer, after the task ends.',
    ],
    [TASK_IDS.WORKING_MEMORY]: () => [
      'First you will hear 4 numbers, like "9-1-2-8". Nothing is written down, you only hear them.',
      'Then you will hear instructions, one at a time. Each one changes the order of the numbers. Keep track in your head.',
      'When the task ends, give the 4 numbers in their new, final order.',
    ],
    [TASK_IDS.AUDITORY_COUNT]: () => [
      'You will hear many short beeps. Some tones are high, some are low.',
      'Count only the high tones in your head. Do not count the low tones.',
      'At the end, say how many high tones you counted.',
      'Use the buttons above to hear an example of the low tone and the high tone before you begin.',
    ],
    [TASK_IDS.SEMANTIC]: () => [
      'You will hear many words, one after another.',
      'The first words all belong to one category. Try to work out what connects them with your eyes closed.',
      'Halfway through, the words quietly change to a new category. Try to notice when this happens, and work out that new connection too.',
      'Give your answers only after the task ends.',
    ],
    [TASK_IDS.VISUOSPATIAL]: () => [
      `The arrow starts at a specific cell, facing a specific direction.`,
      'The arrow moves one cell at a time, it can also change its direction. Follow it with your eyes.',
      'Rows are counted from top to bottom. Columns are counted from left to right.',
      'At the end, give the arrow’s final column, row, and direction.',
    ],
    [TASK_IDS.IDEATION]: () => [
      'Think of as many different uses for a single object as you can.',
      'You will hear the object’s name at the beginning of the task',
      'Generate as many ideas as possible with your eyes closed. Keep them in your head, do not say or write anything yet.',
      'After the task ends, type one idea on each line.',
      'You may type your answer in your preferred language.',
    ],
    [TASK_IDS.DUAL_TASK]: () => [
      'Read this very carefully, because you will not see it again during the task!',
      `Start with the number ${form.startValue}.`,
      `Every time you hear "Update", add ${form.beforeDelta} to your number.`,
      `When you hear "Switch", the rule changes: from then on, add ${form.afterDelta} at every "Update" instead.`,
      'At the same time, count every high tone you hear, from start to finish.',
      'At the end, give your final number and your number of counted high tones.',
    ],
    [TASK_IDS.ANOMALY]: () => [
      form.rule,
      'Watch each code and check it against the rule. When a code breaks the rule, count it in your head.',
      'An example of a incorrect code is "AB-7", which has an extra letter. Another example is "4-C7", which has the wrong order.',
      'Try to remember the different kind of mistakes you encountered (e.g. "an extra letter").',
    ],
    [TASK_IDS.VISUAL_COMPARISON]: () => [
      'Two rows of letters and numbers will update at the same time, again and again.',
      'E.g.: "YF4M-D5AJ-FRYE" and "YF4M-D5AJ-FRYE"',
      'At some point, characters in one row will slowly differ, so the two rows no longer match.',
      'E.g.: "YF4M-D5AJ-FRYE" and "YF4M-D5AM-FRYE"',
      'As soon as you notice the rows are no longer the same, press the DETECT MISMATCH button. Press it only once when you first notice it.',
      'After you press it, stay still until the task ends.',
    ],
    [TASK_IDS.CLOSURE]: () => [
      'A picture is hidden in visual noise. After some time, it will slowly become clearer.',
      'As soon as you can tell what it is, press the RECOGNIZED button. Press it only once you are sure.',
      'After you press it, stay still until the task ends.',
    ],
    [TASK_IDS.SPEECH_NOISE]: () => [
      'You will hear a short passage. There is background noise, so listen carefully.',
      'Just listen during the recording, until it ends.',
      'Afterward, two questions will be shown. Choose your answers from a list of options.',
    ],
    [TASK_IDS.WRITTEN]: () => [
      'Read the text as it appears on the screen, one part at a time.',
      'After you finish reading, think about the main idea. Do not type yet.',
      'At the end, you will pick the main idea from a list and write a short summary in your preferred language.',
    ],
  }[taskId];
  const specific = specificFactory ? specificFactory() : [];
  return [...specific, ...common];
}

// Splits free text into words for every language the app is offered in. The
// battery ships ten locales, and Japanese (like Chinese and Thai) writes
// without spaces between words — splitting on whitespace counted a whole
// Japanese summary as one word, which made Task 12's 35–50 word gate
// impossible to satisfy and blocked submission outright.
function segmentWords(value) {
  const text = String(value || '').trim();
  if (!text) return [];
  if (typeof Intl === 'undefined' || typeof Intl.Segmenter !== 'function') {
    return text.split(/\s+/).filter(Boolean);
  }
  const segments = [...new Intl.Segmenter(undefined, { granularity: 'word' }).segment(text)];
  const words = [];
  for (let index = 0; index < segments.length; index += 1) {
    const { segment, isWordLike } = segments[index];
    if (!isWordLike) continue;
    // ICU reports "well-made" as two word-like segments. Re-joining them keeps
    // this identical to the whitespace splitting it replaced for every
    // space-delimited language, so the change only affects scripts that were
    // previously miscounted.
    const continuesHyphenatedWord = segments[index - 1]?.segment === '-'
      && segments[index - 2]?.isWordLike === true;
    if (continuesHyphenatedWord) words[words.length - 1] += `-${segment}`;
    else words.push(segment);
  }
  return words;
}

export function countWords(value) {
  return segmentWords(value).length;
}

// Han, Kana and Thai are written without spaces between words.
const DENSE_SCRIPT_PATTERN = /[\p{sc=Han}\p{sc=Hiragana}\p{sc=Katakana}\p{sc=Thai}]/u;

const usesDenseScript = (value) => DENSE_SCRIPT_PATTERN.test(String(value || ''));

// Those scripts segment into more words than English for the same content —
// Japanese counts every particle and inflection separately (measured ~1.55x on
// parallel summaries), though Chinese sits near 1x. Rather than a per-language
// table for what is only a coarse validity gate, one generous allowance covers
// all of them: being slightly permissive about length is harmless here, while
// rejecting a valid answer blocks the participant entirely. Minimums need no
// such adjustment — a denser count only makes a minimum easier to clear.
const DENSE_SCRIPT_MAXIMUM_ALLOWANCE = 1.6;

export function maximumWordsFor(text, maximumWords) {
  if (maximumWords == null) return maximumWords;
  return usesDenseScript(text)
    ? Math.round(maximumWords * DENSE_SCRIPT_MAXIMUM_ALLOWANCE)
    : maximumWords;
}

export function normalizedSequence(value) {
  // Task-2 sequences contain non-negative items; hyphens are separators, not
  // unary minus signs (for example "9-4-6-2").
  return String(value || '').match(/\d+(?:\.\d+)?/g)?.map(Number) || [];
}

export function normalizeText(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    // Keep letters, digits and combining marks from every script. The previous
    // a-z0-9 class erased non-Latin text completely (an Arabic or Japanese
    // answer normalized to an empty string) and stripped accents off Latin
    // text ("café" became "caf"). Punctuation is still removed.
    .replace(/[^\p{L}\p{N}\p{M}\s-]/gu, '')
    .replace(/\s+/g, ' ')
    .trim();
}

export const FORM_REGISTRY_FOR_TESTS = ACTIVE_STIMULUS_PACK.formsByTask;
