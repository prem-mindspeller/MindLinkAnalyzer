import React, { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import LoggedInHeader from '../components/LoggedInHeader';
import Footer from '../components/footer';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import {
    faCircleCheck, faMoon, faEye, faStar, faClock,
    faArrowLeft, faArrowRight, faPlay, faTriangleExclamation, faLock,
} from '@fortawesome/free-solid-svg-icons';


import VisualImageryTask from '../components/tasks/VisualImageryTask';
import AttentionFocusTask from '../components/tasks/AttentionFocusTask';
import MentalMathTask from '../components/tasks/MentalMathTask';
import WorkingMemoryTask from '../components/tasks/WorkingMemoryTask';
import LanguageProcessingTask from '../components/tasks/LanguageProcessingTask';
import MotorImageryTask from '../components/tasks/MotorImageryTask';
import CognitiveLoadTask from '../components/tasks/CognitiveLoadTask';
import EmotionFaceTask from '../components/tasks/EmotionFaceTask';
import DiverseThinkingTask from '../components/tasks/DiverseThinkingTask';
import ReappraisalTask from '../components/tasks/ReappraisalTask';
import CuriosityTask from '../components/tasks/CuriosityTask';
import NumFormTask from '../components/tasks/NumFormTask';
import OrderSurpriseTask from '../components/tasks/OrderSurpriseTask';

import '../styles/liveEegReading.css';
import '../styles/taskSelection.css';


const TASK_META = {
    visual_imagery: { name: 'Visual Imagery', duration: 60, eyesClosed: true, description: 'Visual imagery captures the ability to generate and stabilize internal representations without external sensory input. It broadens the assessment to profile imaginative style and simulation strength, differentiating creative individuals from those who strictly excel under structured executive demand', advanced: false },
    attention_focus: { name: 'Focused Attention', duration: 60, eyesClosed: true, description: 'This task isolates the ability to maintain stable internal focus with minimal external stimulation, which is foundational to all other cognitive domains. It evaluates attentional volatility and lapse frequency while providing a clean, low-artefact calibration segment.', advanced: false },
    mental_math: { name: 'Mental Math', duration: 60, eyesClosed: true, description: 'This task imposes controlled executive demand to gauge processing efficiency and cognitive strain without requiring speech or movement. It serves as a primary index for distinguishing individuals who remain neurally efficient under pressure from those who require disproportionate effort.', advanced: false },
    emotion_face: { name: 'Emotion Recognition', duration: 114, eyesClosed: false, description: 'This task introduces affective appraisal into the battery, acting as a bridge between executive and emotional domains. It is highly valuable for evaluating socio-emotional attunement and motivational bias, such as approach versus withdrawal tendencies.', advanced: false },
    working_memory: { name: 'Working Memory', duration: 60, eyesClosed: true, description: 'A dedicated working-memory task isolates cognitive load effects cleanly, enabling interpretable capacity curves. This distinction is vital for separating high-capacity individuals from those who must rely on compensatory effort as task load increases.', advanced: true },
    language_processing: { name: 'Language Processing', duration: 60, eyesClosed: true, description: ' Language tasks introduce a conceptually structured domain that reflects reasoning, communication style, and semantic organization. It helps differentiate participants strong in verbal-semantic integration from those whose strengths lie in imagery or pure cognitive control.', advanced: true },
    motor_imagery: { name: 'Motor Imagery', duration: 60, eyesClosed: true, description: 'This task extends the simulation domain into action-oriented cognition by testing the ability to internally simulate action without overt movement. It complements visual imagery by probing embodied thinking styles and planning biases.', advanced: true },
    cognitive_load: { name: 'Cognitive Load', duration: 60, eyesClosed: true, description: 'This serves as a domain-general executive stress test by monitoring the brains behavior under conflict, switching, and interference. It is critical for understanding an individuals overload threshold and how they coordinate competing demands', advanced: true },
    diverse_thinking: { name: 'Creative Fluency', duration: 96, eyesClosed: false, description: 'Generate creative and unusual uses for two given objects/concepts.', advanced: true },
    reappraisal: { name: 'Perspective Shift', duration: 96, eyesClosed: false, description: 'Deliberately shift perspective on two contrasting scenarios.', advanced: true },
    curiosity: { name: 'Curiosity Reveal', duration: 45, eyesClosed: false, description: 'Watch a short reveal video with full attention and genuine curiosity.', advanced: true },
    num_form: { name: 'Numerical Preference', duration: 60, eyesClosed: false, description: 'Evaluate aesthetic preference between numbers and forms.', advanced: true },
    order_surprise: { name: 'Order & Surprise', duration: 60, eyesClosed: false, description: 'Count symmetrical (ORDER) vs non-symmetrical (SURPRISE) shapes.', advanced: true },
};


const PATHWAY_TASKS = {
    personal: ['working_memory', 'language_processing', 'diverse_thinking', 'motor_imagery', 'cognitive_load'],
    connection: ['motor_imagery', 'cognitive_load', 'reappraisal', 'curiosity'],
    lifestyle: ['motor_imagery', 'cognitive_load', 'order_surprise', 'num_form'],
};

// Always-visible general tasks (no booking required)
const COGNITIVE_TASKS = [
    'visual_imagery', 'attention_focus', 'mental_math', 'emotion_face',
];

// Task id → component
const TASK_COMPONENTS = {
    visual_imagery: VisualImageryTask,
    attention_focus: AttentionFocusTask,
    mental_math: MentalMathTask,
    working_memory: WorkingMemoryTask,
    language_processing: LanguageProcessingTask,
    motor_imagery: MotorImageryTask,
    cognitive_load: CognitiveLoadTask,
    emotion_face: EmotionFaceTask,
    diverse_thinking: DiverseThinkingTask,
    reappraisal: ReappraisalTask,
    curiosity: CuriosityTask,
    num_form: NumFormTask,
    order_surprise: OrderSurpriseTask,
};


const TaskSelection = () => {
    const navigate = useNavigate();
    const { t } = useTranslation();
    const pathway = sessionStorage.getItem('selectedPathway') || 'personal';
    const hasAdvancedBooking = sessionStorage.getItem('hasAdvancedBooking') === 'true';

    // Build visible task list: cognitive + pathway-specific advanced
    const advancedTaskIds = PATHWAY_TASKS[pathway] || [];
    const visibleTaskIds = [...COGNITIVE_TASKS, ...advancedTaskIds];

    const [selectedId, setSelectedId] = useState(visibleTaskIds[0] || null);
    const [activeTaskId, setActiveTaskId] = useState(null); // currently executing
    const [completedIds, setCompletedIds] = useState(() => {
        try { return JSON.parse(sessionStorage.getItem('completedTasks') || '[]'); }
        catch { return []; }
    });

    const selectedMeta = selectedId ? TASK_META[selectedId] : null;

    const handleStartTask = useCallback(() => {
        if (selectedId) setActiveTaskId(selectedId);
    }, [selectedId]);

    const handleTaskComplete = useCallback((taskId, samples) => {
        // Save samples to sessionStorage
        const key = `taskData_${taskId}`;
        const existing = JSON.parse(sessionStorage.getItem(key) || '[]');
        sessionStorage.setItem(key, JSON.stringify([...existing, ...samples]));

        // Mark complete
        const updated = [...new Set([...completedIds, taskId])];
        setCompletedIds(updated);
        sessionStorage.setItem('completedTasks', JSON.stringify(updated));

        setActiveTaskId(null);
    }, [completedIds, visibleTaskIds, hasAdvancedBooking]);

    const handleTaskBack = useCallback(() => {
        setActiveTaskId(null);
    }, []);

    if (activeTaskId) {
        const TaskComp = TASK_COMPONENTS[activeTaskId];
        return (
            <div className="app-container">
                <LoggedInHeader />
                <main className="app-main">
                    <div className="task-selection-page">
                        <div className="ts-task-exec-header">
                            <h1 className="ts-page-title">{t(`taskMeta.${activeTaskId}.name`, { defaultValue: TASK_META[activeTaskId]?.name })}</h1>
                            <p className="ts-page-subtitle">{t('taskSelection.taskSubtitle')}</p>
                        </div>
                        <TaskComp
                            onComplete={(samples) => handleTaskComplete(activeTaskId, samples)}
                            onBack={handleTaskBack}
                        />
                    </div>
                </main>
                <Footer />
            </div>
        );
    }


    const pathwayLabel = {
        personal: t('taskSelection.pathwayPersonal'),
        connection: t('taskSelection.pathwayConnection'),
        lifestyle: t('taskSelection.pathwayLifestyle'),
    }[pathway] || pathway;

    return (
        <div className="app-container">
            <LoggedInHeader />
            <main className="app-main">
                <div className="task-selection-page">

                    <div className="ts-page-header">
                        <h1 className="ts-page-title">{t('tasks.title')}</h1>
                        <p className="ts-page-subtitle">{t('taskSelection.subtitle', { pathway: pathwayLabel })}</p>
                    </div>

                    <div className="ts-layout">
                        {/* ── Task list ── */}
                        <div className="ts-task-list">
                            {/* General tasks group */}
                            <p className="ts-group-label">
                                {t('taskSelection.generalTasks')}
                                <span className="ts-group-progress">
                                    {COGNITIVE_TASKS.filter(id => completedIds.includes(id)).length}/{COGNITIVE_TASKS.length}
                                </span>
                            </p>
                            {COGNITIVE_TASKS.map(id => {
                                const meta = TASK_META[id];
                                const done = completedIds.includes(id);
                                return (
                                    <button
                                        key={id}
                                        className={`ts-task-item${selectedId === id ? ' selected' : ''}${done ? ' done' : ''}`}
                                        onClick={() => setSelectedId(id)}
                                    >
                                        <span className="ts-task-item-icon">
                                            {done
                                                ? <FontAwesomeIcon icon={faCircleCheck} />
                                                : meta.eyesClosed
                                                    ? <FontAwesomeIcon icon={faMoon} />
                                                    : <FontAwesomeIcon icon={faEye} />}
                                        </span>
                                        <span className="ts-task-item-name">{t(`taskMeta.${id}.name`, { defaultValue: meta.name })}</span>
                                        <span className="ts-task-item-dur">{meta.duration}s</span>
                                    </button>
                                );
                            })}

                            {/* Advanced tasks group */}
                            {advancedTaskIds.length > 0 && (
                                <>
                                    <p className="ts-group-label" style={{ marginTop: 16 }}>
                                        {t('taskSelection.advancedTasks', { pathway: pathwayLabel })}
                                    </p>
                                    {advancedTaskIds.map(id => {
                                        const meta = TASK_META[id];
                                        const done = completedIds.includes(id);
                                        const locked = !hasAdvancedBooking;
                                        return (
                                            <button
                                                key={id}
                                                className={`ts-task-item ts-task-item-advanced${selectedId === id ? ' selected' : ''}${done ? ' done' : ''}${locked ? ' locked' : ''}`}
                                                onClick={() => !locked && setSelectedId(id)}
                                                disabled={locked}
                                            >
                                                <span className="ts-task-item-icon">
                                                    {locked
                                                        ? <FontAwesomeIcon icon={faLock} />
                                                        : done
                                                            ? <FontAwesomeIcon icon={faCircleCheck} />
                                                            : <FontAwesomeIcon icon={faStar} />}
                                                </span>
                                                <span className="ts-task-item-name">{t(`taskMeta.${id}.name`, { defaultValue: meta.name })}</span>
                                                <span className="ts-task-item-dur">{locked ? t('taskSelection.locked') : `${meta.duration}s`}</span>
                                            </button>
                                        );
                                    })}
                                </>
                            )}
                        </div>

                        {/* ── Task detail panel ── */}
                        <div className="ts-detail-panel">
                            {selectedMeta ? (
                                <>
                                    <h2 className="ts-detail-name">
                                        {completedIds.includes(selectedId) && <span className="ts-done-badge"><FontAwesomeIcon icon={faCircleCheck} style={{ marginRight: 4 }} />{t('taskSelection.completed')}</span>}
                                        {t(`taskMeta.${selectedId}.name`, { defaultValue: selectedMeta.name })}
                                    </h2>

                                    <div className="ts-detail-tags">
                                        <span className={`ts-tag${selectedMeta.eyesClosed ? ' tag-ec' : ' tag-eo'}`}>
                                            {selectedMeta.eyesClosed
                                                ? <><FontAwesomeIcon icon={faMoon} style={{ marginRight: 4 }} />{t('taskSelection.eyesClosed')}</>
                                                : <><FontAwesomeIcon icon={faEye} style={{ marginRight: 4 }} />{t('taskSelection.eyesOpen')}</>}
                                        </span>
                                        <span className="ts-tag tag-dur"><FontAwesomeIcon icon={faClock} style={{ marginRight: 4 }} />{selectedMeta.duration}s</span>
                                        {selectedMeta.advanced && <span className="ts-tag tag-adv"><FontAwesomeIcon icon={faStar} style={{ marginRight: 4 }} />{t('taskSelection.advanced')}</span>}
                                    </div>

                                    {completedIds.length >= 4 && (
                                        <p className="ts-detail-desc">{t(`taskMeta.${selectedId}.description`, { defaultValue: selectedMeta.description })}</p>
                                    )}

                                    {completedIds.includes(selectedId) ? (
                                        <p className="ts-already-done">
                                            <FontAwesomeIcon icon={faTriangleExclamation} style={{ marginRight: 6 }} />
                                            {t('taskSelection.alreadyDone')}
                                        </p>
                                    ) : null}

                                    <button
                                        className="ts-start-btn"
                                        onClick={handleStartTask}
                                    >
                                        <FontAwesomeIcon icon={faPlay} style={{ marginRight: 8 }} />
                                        {completedIds.includes(selectedId) ? t('taskSelection.runAgain') : t('taskSelection.taskInstructions')}
                                    </button>
                                </>
                            ) : (
                                <p className="ts-detail-placeholder">{t('taskSelection.selectPlaceholder')}</p>
                            )}
                        </div>
                    </div>

                    <div className="navigation-buttons-eeg">
                        <button className="btn-back-eeg" onClick={() => navigate(-1)}>
                            <FontAwesomeIcon icon={faArrowLeft} style={{ marginRight: 6 }} />{t('nav.back')}
                        </button>
                        <button
                            className="btn-next-eeg"
                            disabled={completedIds.length <= 3}
                            onClick={() => navigate('/upload')}
                        >
                            {t('nav.next')} <FontAwesomeIcon icon={faArrowRight} style={{ marginLeft: 6 }} />
                        </button>
                    </div>
                </div>
            </main>
            <Footer />
        </div>
    );
};

export default TaskSelection;
