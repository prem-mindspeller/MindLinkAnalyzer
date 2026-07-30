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
    description: 'Silently maintain one spoken calculation chain as its pace and operation mix increase.',
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
    description: 'Maintain and update a spoken sequence without giving an intermediate answer.',
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
    description: 'Count high tones silently in a continuous, irregular stream while ignoring low tones.',
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
    description: 'Infer two organising principles from one uninterrupted spoken word stream and notice the switch.',
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
    description: 'Track a centrally displayed arrow as every route turn changes its position and orientation.',
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
    description: 'Generate varied uses for one prompt silently, then capture the ideas only after EEG scoring stops.',
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
    description: 'Count targets while updating a number, then apply one new update rule without pausing.',
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
    description: 'Monitor one continuous code stream against a stated rule and report anomalies only afterward.',
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
    description: 'Watch two centrally aligned strings and press once when a single gradual mismatch appears.',
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
    description: 'Search for one target in dense visual noise and respond once when it becomes recognizable.',
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
    description: 'Listen silently to one continuous passage in moderate background noise and answer afterward.',
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
    description: 'Read a centrally paced passage, plan a synthesis silently, then write only after EEG stops.',
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

const NUMERICAL_FORMS = [
  numericalForm('num_a', 18,
    [{ op: 'add', value: 7 }, { op: 'multiply', value: 2 }, { op: 'subtract', value: 6 }, { op: 'add', value: 5 }, { op: 'subtract', value: 4 }, { op: 'add', value: 8 }],
    [{ op: 'add', value: 7 }, { op: 'divide', value: 2 }, { op: 'add', value: 13 }, { op: 'multiply', value: 2 }, { op: 'subtract', value: 11 }, { op: 'add', value: 5 }, { op: 'divide', value: 4 }, { op: 'multiply', value: 3 }, { op: 'subtract', value: 17 }, { op: 'add', value: 9 }]),
  numericalForm('num_b', 24,
    [{ op: 'subtract', value: 5 }, { op: 'add', value: 8 }, { op: 'multiply', value: 2 }, { op: 'subtract', value: 9 }, { op: 'add', value: 7 }, { op: 'subtract', value: 4 }],
    [{ op: 'divide', value: 2 }, { op: 'add', value: 15 }, { op: 'multiply', value: 2 }, { op: 'subtract', value: 18 }, { op: 'divide', value: 3 }, { op: 'add', value: 11 }, { op: 'multiply', value: 2 }, { op: 'subtract', value: 7 }, { op: 'add', value: 5 }, { op: 'divide', value: 2 }]),
  numericalForm('num_c', 15,
    [{ op: 'add', value: 9 }, { op: 'multiply', value: 2 }, { op: 'subtract', value: 8 }, { op: 'add', value: 6 }, { op: 'subtract', value: 11 }, { op: 'add', value: 5 }],
    [{ op: 'multiply', value: 2 }, { op: 'subtract', value: 14 }, { op: 'divide', value: 3 }, { op: 'add', value: 16 }, { op: 'multiply', value: 2 }, { op: 'subtract', value: 20 }, { op: 'divide', value: 2 }, { op: 'add', value: 17 }, { op: 'subtract', value: 9 }, { op: 'multiply', value: 2 }]),
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

const IDEATION_FORMS = [
  { id: 'ideas_a', prompt: 'Generate as many different uses as possible for a brick.' },
  { id: 'ideas_b', prompt: 'Generate as many different uses as possible for a paper cup.' },
  { id: 'ideas_c', prompt: 'Generate as many different uses as possible for a shoelace.' },
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
    rule: 'Every code must contain exactly one letter, a hyphen, and two digits in that same order.',
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

function visualComparisonForm(id, seed, mismatchOnset, mismatchIndex, replacementOffset) {
  const presentation = taskPresentationFor(TASK_IDS.VISUAL_COMPARISON);
  const updateIntervalSeconds = presentation.updateIntervalSeconds;
  const frameCount = Math.ceil(
    TASK_DEFINITIONS[TASK_IDS.VISUAL_COMPARISON].duration / updateIntervalSeconds,
  ) + 1;
  const random = seededUnit(seed);
  const frames = Array.from({ length: frameCount }, () => comparisonCode(random));
  if (frames.some((code) => code[mismatchIndex] === '-')) {
    throw new Error(`${id} mismatch position must contain a code character in every frame`);
  }
  return {
    id,
    frames,
    updateIntervalSeconds,
    mismatchIndex,
    replacementOffset,
    mismatchOnset,
    mismatchRevealSeconds: presentation.mismatchRevealSeconds,
  };
}

const VISUAL_COMPARISON_FORMS = [
  visualComparisonForm('compare_a', 9101, 25, 11, 5),
  visualComparisonForm('compare_b', 9102, 26, 6, 7),
  visualComparisonForm('compare_c', 9103, 24, 13, 9),
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
    passage: 'A coastal town had flooded every winter for decades. Instead of building one higher wall, residents restored dunes, widened a marsh, and raised the lowest footpaths. The first storm after the project still brought high water, but the marsh slowed the surge and the dunes protected homes from waves. Engineers warned that no single measure could remove all risk. The council therefore paired the landscape work with clear evacuation routes and regular warning tests. The project succeeded because natural barriers, practical planning, and community preparation supported one another. It also created new habitat and made the shoreline easier to visit during calm weather.',
    continuation: 'Before construction began, surveyors mapped where water entered streets and where older residents would need help leaving their homes. Volunteers then practised the new routes during dry weather, which revealed that one bridge was too narrow for emergency vehicles. The plan was adjusted before the next storm season. Local businesses agreed to store temporary barriers, while schools added flood instructions to their safety exercises. Measurements after each storm were compared with earlier records so that the dunes and marsh could be repaired where erosion was greatest. Some residents initially wanted a single visible defence because it appeared simpler. Public workshops showed why several linked measures offered more resilience: if one element was damaged, the others could still reduce harm. The council published maintenance costs and inspection results rather than treating the opening ceremony as the end of the project. This ongoing review helped the town adapt as sea levels and weather patterns changed. The approach did not promise perfect safety. It combined natural protection, reliable infrastructure, warnings, evacuation practice, and shared responsibility so that the remaining risk could be managed openly.',
    mainIdea: 'Layered natural and practical measures reduced flood risk.',
    mainIdeaOptions: ['Layered natural and practical measures reduced flood risk.', 'The town stopped all storms by building one wall.', 'Tourism was the only reason for restoring the shore.'],
    keyDetailQuestion: 'What slowed the storm surge?',
    keyDetail: 'the marsh',
  },
  {
    id: 'speech_b',
    passage: 'A hospital noticed that medicine deliveries were often late, even though every department worked quickly. A review showed that each team used a different naming system, so staff repeatedly paused to check labels. The hospital introduced one shared code, placed frequently used supplies closer to the wards, and scheduled short handover checks. Delivery time improved without asking anyone to work faster. The lesson was that delays came mainly from coordination and layout, not from individual effort. Managers kept a manual backup because a shared digital system can still fail. After three months, errors had fallen and nurses spent more time with patients.',
    continuation: 'The review team followed several orders from the pharmacy to the bedside and recorded every handoff. They found that small uncertainties accumulated: a storage room used an abbreviated ward name, a trolley was restocked at unpredictable times, and urgent requests travelled through the same queue as routine supplies. Staff from nursing, pharmacy, logistics, and information technology designed the changes together. They tested the shared code on one floor, checked whether labels remained readable under different lighting, and invited night-shift workers to report problems. When one code was easily confused with another, it was changed before wider use. The hospital also displayed who was responsible for resolving each type of exception. Weekly data showed where delays moved rather than assuming that a faster average meant every ward had improved. Training focused on the common process and on when to use the manual fallback. No individual team lost professional judgement; the shared system removed avoidable translation between teams. By making responsibilities, locations, and labels consistent, the hospital reduced waiting and mistakes while preserving a safe route for unusual cases and technical failures.',
    mainIdea: 'Shared systems and layout changes improved medicine delivery.',
    mainIdeaOptions: ['Shared systems and layout changes improved medicine delivery.', 'Nurses were told to walk faster.', 'The hospital removed all manual backups.'],
    keyDetailQuestion: 'Why did staff repeatedly pause?',
    keyDetail: 'to check different labels',
  },
  {
    id: 'speech_c',
    passage: 'A school library wanted more students to use its science collection. Buying extra books had made little difference, so the librarian tested a new approach. Small themed displays connected science topics to current school projects, and teachers received brief guides showing where relevant material could be found. Students could also leave questions on a board for the next class to answer. Borrowing increased, but the most important change was that students began discussing sources and comparing explanations. The library kept the displays temporary so topics could change with classroom needs. Access improved because information became visible, timely, and connected to a purpose.',
    continuation: 'At first, the displays covered a space project and a local water-quality investigation. Each included books at several reading levels, a diagram, a short article, and a prompt that could be answered with more than one source. Teachers brought classes to the display before assigning research, so students saw how the materials related to a question they already understood. The librarian tracked not only loans but also which questions appeared on the board and which sources students cited in their answers. When a display produced little discussion, its labels and position were changed. Students helped choose later themes and recommended explanations that they had found clear. Older classes recorded brief source guides for younger readers, but every recommendation still identified the author and publication date. The project did not replace the catalogue or quiet reading areas. It created an inviting entrance into the collection and then taught students how to explore beyond the first item. Regular rotation also prevented one popular topic from occupying the space permanently. The useful change was therefore not simply decoration or a larger stock of books. Resources became easier to notice, connected to current work, and supported by questions that encouraged comparison and conversation.',
    mainIdea: 'Connecting visible resources to current projects increased meaningful use.',
    mainIdeaOptions: ['Connecting visible resources to current projects increased meaningful use.', 'The library succeeded only by buying many new books.', 'Permanent displays prevented topics from changing.'],
    keyDetailQuestion: 'Where could students leave questions?',
    keyDetail: 'on a board',
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
    passage: 'Cities often respond to summer heat by adding mechanical cooling, yet neighbourhood design can reduce the problem before electricity is used. Trees shade walls and pavement, while soil and vegetation release stored water slowly into the air. Light-coloured roofs absorb less solar energy than dark roofs. These measures work at different scales: a roof mainly changes one building, whereas a connected canopy can cool a walking route and nearby homes. Their benefits are not automatic. Young trees need years of care, reflective materials can create glare if placed badly, and scarce water may limit planting. Effective heat planning therefore combines local climate data, maintenance budgets, and input from residents who know where people wait, walk, and gather. The strongest strategy is rarely a single technology. It is a coordinated set of physical changes, operating plans, and social protections, evaluated over time. Cooling centres remain important during extreme events, especially for residents whose homes cannot be upgraded quickly. Long-term design and emergency support solve different parts of the same risk.',
    mainIdea: 'Urban heat is best reduced through coordinated design, maintenance, and emergency support.',
    mainIdeaOptions: ['Urban heat is best reduced through coordinated design, maintenance, and emergency support.', 'Mechanical cooling should be removed from every building.', 'Planting trees is immediate and has no maintenance cost.'],
  },
  {
    id: 'written_b',
    passage: 'Teams often assume that more data will automatically produce better decisions. In practice, additional measures can obscure the question if nobody agrees what action each measure should inform. A useful dashboard begins with decisions, not charts. Designers identify who must decide, how often the decision occurs, and what threshold would change the response. They then select the smallest set of reliable indicators that can reveal that threshold. Context still matters: a sudden change may reflect a reporting delay rather than a real shift in performance. For that reason, strong dashboards pair numbers with definitions, update times, and clear ownership. They also preserve a route back to source data for investigation. Simplicity does not mean hiding uncertainty. It means presenting uncertainty where it affects action and removing decoration that competes with it. Reviews should retire indicators that are never used and test whether users interpret alerts consistently. A dashboard succeeds when it shortens the path from evidence to a justified decision, not when it contains the greatest possible number of metrics.',
    mainIdea: 'Decision-focused dashboards use a small, reliable and well-explained set of indicators.',
    mainIdeaOptions: ['Decision-focused dashboards use a small, reliable and well-explained set of indicators.', 'The best dashboard always contains the largest number of charts.', 'Uncertainty should always be hidden from users.'],
  },
  {
    id: 'written_c',
    passage: 'Repairing products can conserve resources, but repairability depends on choices made long before an item breaks. Fasteners that can be opened, replaceable modules, available diagrams, and stable software support all influence whether a technician can restore a device. A product may be technically repairable yet practically discarded if parts arrive too slowly or cost almost as much as replacement. Policy can improve access to information and components, while manufacturers can design upgrades that extend useful life. Consumers also need trustworthy guidance, because an unsafe repair can create new risks. Repair is therefore an ecosystem rather than a single workshop activity. Designers, suppliers, service networks, regulators, and users each control part of the outcome. Measuring success only by the number of repairs misses prevention: durable construction and careful maintenance can delay failure altogether. A strong circular strategy combines durability, maintenance, repair, reuse, and responsible recycling. Each option should be chosen according to safety, environmental impact, cost, and the condition of the product.',
    mainIdea: 'Repairability depends on a coordinated ecosystem across design, supply, service, policy, and users.',
    mainIdeaOptions: ['Repairability depends on a coordinated ecosystem across design, supply, service, policy, and users.', 'Every broken product should be repaired regardless of safety or cost.', 'Repairability is controlled only by technicians in workshops.'],
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
  if (!frames.length) return { base: '', changed: '', mismatchIndex: -1 };
  const elapsed = Number.isFinite(Number(elapsedSeconds)) ? Math.max(0, Number(elapsedSeconds)) : 0;
  const interval = Math.max(0.1, Number(form.updateIntervalSeconds) || 1);
  const frameIndex = Math.min(frames.length - 1, Math.floor(elapsed / interval));
  const base = frames[frameIndex];
  const characters = [...base];
  characters[form.mismatchIndex] = comparisonReplacement(
    characters[form.mismatchIndex],
    form.replacementOffset,
  );
  return {
    base,
    changed: characters.join(''),
    mismatchIndex: form.mismatchIndex,
    frameIndex,
  };
}

export function pacedPassageChunk(form, elapsedSeconds, options = {}) {
  const words = String(form?.passage || '').trim().split(/\s+/).filter(Boolean);
  if (!words.length) return '';
  const presentation = taskPresentationFor(TASK_IDS.WRITTEN);
  const readingDuration = Number(options.readingDurationSeconds)
    || Number(form?.readingDurationSeconds)
    || presentation.readingDurationSeconds;
  const chunkCount = Number(options.chunkCount)
    || Number(form?.chunkCount)
    || presentation.chunkCount;
  const chunkIndex = Math.min(chunkCount - 1, Math.floor((elapsedSeconds / readingDuration) * chunkCount));
  const chunkSize = Math.ceil(words.length / chunkCount);
  return words.slice(chunkIndex * chunkSize, (chunkIndex + 1) * chunkSize).join(' ');
}

export function taskIntroduction(taskId, form) {
  const definition = TASK_DEFINITIONS[taskId];
  const common = [
    `This is one uninterrupted ${definition.duration}-second EEG scoring block.`,
    `Keep your eyes ${definition.eyeState} and minimise blinking, jaw tension, and movement.`,
    'Do not speak or type until the recording has ended and the response form appears.',
  ];
  const specificFactory = {
    [TASK_IDS.NUMERICAL]: () => [`Start at ${form.startValue}; follow every spoken operation silently and give only the final value.`],
    [TASK_IDS.WORKING_MEMORY]: () => ['The initial sequence is presented only after EEG scoring starts. Encode it then, maintain every spoken update, and report only the final order.'],
    [TASK_IDS.AUDITORY_COUNT]: () => ['Count every high tone silently and ignore the low tones. Report one count afterward.', 'Use the buttons above to hear an example of the low tone and the high tone before you begin.'],
    [TASK_IDS.SEMANTIC]: () => ['Infer the organising principle of the first word stream and the new principle after the seamless switch.'],
    [TASK_IDS.VISUOSPATIAL]: () => [`Start at row ${form.start.y + 1}, column ${form.start.x + 1}, facing ${form.start.orientation}. Every displayed turn changes both direction and grid position. Row numbers run top to bottom and columns left to right.`],
    [TASK_IDS.IDEATION]: () => [`Prompt: ${form.prompt}`, 'Generate ideas silently; you will capture each idea on a separate line afterward.'],
    [TASK_IDS.DUAL_TASK]: () => [`Start at ${form.startValue}. Before the switch, ${form.beforeDelta < 0 ? `subtract ${Math.abs(form.beforeDelta)}` : `add ${form.beforeDelta}`} at every “Update” cue. After “Switch”, ${form.afterDelta < 0 ? `subtract ${Math.abs(form.afterDelta)}` : `add ${form.afterDelta}`} at every “Update” cue. Count high tones throughout.`],
    [TASK_IDS.ANOMALY]: () => [form.rule, 'Silently count anomalies and remember their types; do not click during the stream.'],
    [TASK_IDS.VISUAL_COMPARISON]: () => ['Maintain central gaze while both code strings update in synchrony. Press DETECT once, as soon as one gradual mismatch appears, then remain still until the timed block ends.'],
    [TASK_IDS.CLOSURE]: () => ['A fragmented target will emerge gradually from dense visual noise. Press RECOGNIZED once when you know what it is, then remain still until the timed block ends.'],
    [TASK_IDS.SPEECH_NOISE]: () => ['Listen to the entire passage in moderate background noise. Answer only after the sound and EEG scoring stop.'],
    [TASK_IDS.WRITTEN]: () => ['Read each centrally paced section. Then plan a concise synthesis silently; typing begins only after EEG stops.'],
  }[taskId];
  const specific = specificFactory ? specificFactory() : [];
  return [...specific, ...common];
}

export function countWords(value) {
  return String(value || '').trim().split(/\s+/).filter(Boolean).length;
}

export function normalizedSequence(value) {
  // Task-2 sequences contain non-negative items; hyphens are separators, not
  // unary minus signs (for example "9-4-6-2").
  return String(value || '').match(/\d+(?:\.\d+)?/g)?.map(Number) || [];
}

export function normalizeText(value) {
  return String(value || '').trim().toLowerCase().replace(/[^a-z0-9\s-]/g, '').replace(/\s+/g, ' ');
}

export const FORM_REGISTRY_FOR_TESTS = ACTIVE_STIMULUS_PACK.formsByTask;
