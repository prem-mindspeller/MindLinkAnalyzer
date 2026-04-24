import React from 'react';
import { useTranslation } from 'react-i18next';
import TaskRunner from './TaskRunner';
import face1 from '../../../../assets/emo_face_01.png';
import face2 from '../../../../assets/emo_face_02.png';
import face3 from '../../../../assets/emo_face_03.png';
import face4 from '../../../../assets/emo_face_04.png';
import face5 from '../../../../assets/emo_face_05.png';
import face6 from '../../../../assets/emo_face_06.png';

const EmotionFaceTask = ({ onComplete, onBack }) => {
    const { t } = useTranslation();
    const cue = t('taskContent.emotionFace.cueInstruction');
    const phases = [
        { type: 'cue', duration: 8, record: true, instruction: cue },
        { type: 'viewing', duration: 11, record: true, instruction: ' ', image: face1 },
        { type: 'cue', duration: 8, record: true, instruction: cue },
        { type: 'viewing', duration: 11, record: true, instruction: ' ', image: face2 },
        { type: 'cue', duration: 8, record: true, instruction: cue },
        { type: 'viewing', duration: 11, record: true, instruction: ' ', image: face3 },
        { type: 'cue', duration: 8, record: true, instruction: cue },
        { type: 'viewing', duration: 11, record: true, instruction: ' ', image: face4 },
        { type: 'cue', duration: 8, record: true, instruction: cue },
        { type: 'viewing', duration: 11, record: true, instruction: ' ', image: face5 },
        { type: 'cue', duration: 8, record: true, instruction: cue },
        { type: 'viewing', duration: 11, record: true, instruction: ' ', image: face6 },
    ];
    return (
        <TaskRunner
            phases={phases}
            taskName={t('taskContent.emotionFace.name')}
            eyesClosed={false}
            introText={[
                t('taskContent.emotionFace.introLine1'),
                t('taskContent.emotionFace.introLine2'),
                t('taskContent.emotionFace.introLine3'),
                t('taskContent.emotionFace.introLine4'),
            ]}
            onComplete={onComplete}
            onBack={onBack}
        />
    );
};

export default EmotionFaceTask;
