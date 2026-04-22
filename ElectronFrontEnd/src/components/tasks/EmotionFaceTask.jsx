import React from 'react';
import TaskRunner from './TaskRunner';
import face1 from '../../../../assets/emo_face_01.png';
import face2 from '../../../../assets/emo_face_02.png';
import face3 from '../../../../assets/emo_face_03.png';
import face4 from '../../../../assets/emo_face_04.png';
import face5 from '../../../../assets/emo_face_05.png';
import face6 from '../../../../assets/emo_face_06.png';

const PHASES = [
    { type: 'cue', duration: 8, record: true, instruction: 'INSTRUCTION: Prepare for the upcoming face.' },
    { type: 'viewing', duration: 11, record: true, instruction: ' ', image: face1 },
    { type: 'cue', duration: 8, record: true, instruction: 'INSTRUCTION: Prepare for the upcoming face.' },
    { type: 'viewing', duration: 11, record: true, instruction: ' ', image: face2 },
    { type: 'cue', duration: 8, record: true, instruction: 'INSTRUCTION: Prepare for the upcoming face.' },
    { type: 'viewing', duration: 11, record: true, instruction: ' ', image: face3 },
    { type: 'cue', duration: 8, record: true, instruction: 'INSTRUCTION: Prepare for the upcoming face.' },
    { type: 'viewing', duration: 11, record: true, instruction: ' ', image: face4 },
    { type: 'cue', duration: 8, record: true, instruction: 'INSTRUCTION: Prepare for the upcoming face.' },
    { type: 'viewing', duration: 11, record: true, instruction: ' ', image: face5 },
    { type: 'cue', duration: 8, record: true, instruction: 'INSTRUCTION: Prepare for the upcoming face.' },
    { type: 'viewing', duration: 11, record: true, instruction: ' ', image: face6 },
];

const EmotionFaceTask = ({ onComplete, onBack }) => (
    <TaskRunner
        phases={PHASES}
        taskName="Emotion Recognition"
        eyesClosed={false}
        introText="In a moment, you will see a series of faces.
Simply look at each face and allow yourself to naturally experience your reaction to it.
There is no need to label or analyze the emotion—just notice how the face affects you.
Keep your gaze on the screen and respond naturally."
        onComplete={onComplete}
        onBack={onBack}
    />
);

export default EmotionFaceTask;
