import React from "react";
import { useTranslation } from 'react-i18next';
import "../../styles/main.css";

const STEP_IDS = [1, 2, 3, 4, 5, 6, 7];

const StepsComponent = ({ currentStep = 1 }) => {
    const { t } = useTranslation();
    const STEPS = STEP_IDS.map(n => ({
        number: n,
        label: t(`stepsData.${n}.label`),
        description: t(`stepsData.${n}.description`),
    }));
    return (
        <div className="steps-wrapper">
            <ol className="steps-list">
                {STEPS.map((step, index) => {
                    const isCompleted = step.number < currentStep;
                    const isActive = step.number === currentStep;
                    const isLast = index === STEPS.length - 1;

                    return (
                        <li key={step.number} className="steps-item">
                            {/* Connector line */}
                            {!isLast && (
                                <div className={`steps-connector${isCompleted ? ' steps-connector--completed' : ''}`} />
                            )}

                            {/* Step circle */}
                            <div className={`steps-circle${isCompleted ? ' steps-circle--completed' : isActive ? ' steps-circle--active' : ' steps-circle--pending'}`}>
                                {isCompleted ? (
                                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                                        <path d="M3 8l3.5 3.5L13 5" stroke="white" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
                                    </svg>
                                ) : step.number}
                            </div>

                            {/* Step content */}
                            <div className={`steps-content${isLast ? ' steps-content--last' : ''}`}>
                                <p className={`steps-label${isActive ? ' steps-label--active' : isCompleted ? ' steps-label--completed' : ' steps-label--pending'}`}>
                                    {step.label}
                                </p>
                                <p className={`steps-description${isActive ? ' steps-description--active' : ''}`}>
                                    {step.description}
                                </p>
                            </div>
                        </li>
                    );
                })}
            </ol>
        </div>
    );
};

export default StepsComponent;