import React from 'react';
import { useTranslation } from 'react-i18next';
import TaskRunner from './TaskRunner';

const SemanticMemoryTask = ({ onComplete, onBack }) => {
    const { t } = useTranslation();

    // 5 segments × 10 s = 50 s total (all continuously recorded)
    const phases = [
        { type: 'task', duration: 10, record: true,  instruction: t('taskContent.semanticMemory.phase1') },
        { type: 'cue',  duration: 10, record: true,  instruction: t('taskContent.semanticMemory.rest1')  },
        { type: 'task', duration: 10, record: true,  instruction: t('taskContent.semanticMemory.phase2') },
        { type: 'cue',  duration: 10, record: true,  instruction: t('taskContent.semanticMemory.rest2')  },
        { type: 'task', duration: 10, record: true,  instruction: t('taskContent.semanticMemory.phase3') },
    ];

    return (
        <TaskRunner
            phases={phases}
            taskName={t('taskContent.semanticMemory.name')}
            eyesClosed={true}
            introText={[
                t('taskContent.semanticMemory.intro1'),
                t('taskContent.semanticMemory.intro2'),
                t('taskContent.semanticMemory.intro3'),
                t('taskContent.semanticMemory.intro4'),
                t('taskContent.semanticMemory.intro5'),
                t('taskContent.semanticMemory.intro6'),
            ]}
            onComplete={onComplete}
            onBack={onBack}
        />
    );
};

export default SemanticMemoryTask;
