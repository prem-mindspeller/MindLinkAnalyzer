import React from 'react';
import { useTranslation } from 'react-i18next';
import TaskRunner from './TaskRunner';

const SemanticMemoryTask = ({ onComplete, onBack }) => {
    const { t } = useTranslation();

    const phases = [
        {
            type: 'task',
            duration: 10,
            record: true,
            instruction: t('taskContent.semanticMemory.phase1', {
                defaultValue: 'PEOPLE: Think of names of people you know. Eyes closed.',
            }),
        },
        {
            type: 'cue',
            duration: 10,
            record: true,
            instruction: t('taskContent.semanticMemory.rest1', {
                defaultValue: 'REST: Relax and let your mind go blank. Eyes closed.',
            }),
        },
        {
            type: 'task',
            duration: 10,
            record: true,
            instruction: t('taskContent.semanticMemory.phase2', {
                defaultValue: 'CITIES: Think of names of cities you know. Eyes closed.',
            }),
        },
        {
            type: 'cue',
            duration: 10,
            record: true,
            instruction: t('taskContent.semanticMemory.rest2', {
                defaultValue: 'REST: Relax again. Eyes closed.',
            }),
        },
        {
            type: 'task',
            duration: 10,
            record: true,
            instruction: t('taskContent.semanticMemory.phase3', {
                defaultValue: 'OBJECTS: Think of common objects around you. Eyes closed.',
            }),
        },
    ];

    return (
        <TaskRunner
            phases={phases}
            taskName={t('taskContent.semanticMemory.name', { defaultValue: 'Semantic Memory Retrieval' })}
            eyesClosed={true}
            introText={[
                t('taskContent.semanticMemory.intro1', {
                    defaultValue: 'This is a structured memory retrieval task with 5 alternating segments of 10 seconds each.',
                }),
                t('taskContent.semanticMemory.intro2', {
                    defaultValue: 'Segment 1: think of names of people you know.',
                }),
                t('taskContent.semanticMemory.intro3', {
                    defaultValue: 'Segment 2: rest and let your mind go blank.',
                }),
                t('taskContent.semanticMemory.intro4', {
                    defaultValue: 'Segment 3: think of names of cities you know.',
                }),
                t('taskContent.semanticMemory.intro5', {
                    defaultValue: 'Segment 4: rest again.',
                }),
                t('taskContent.semanticMemory.intro6', {
                    defaultValue: 'Segment 5: think of common objects around you.',
                }),
            ]}
            onComplete={onComplete}
            onBack={onBack}
        />
    );
};

export default SemanticMemoryTask;
