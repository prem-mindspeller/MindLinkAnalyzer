import React from 'react';
import { useNavigate } from 'react-router-dom';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faCircleCheck, faVolumeHigh } from '@fortawesome/free-solid-svg-icons';

const WarningComponent = () => {
    const navigate = useNavigate();
    return (
        <div className="warning-card">
            <p className="warning-card-title">Before you sign in, make sure your headset is:</p>
            <ul className="warning-checklist">
                <li><FontAwesomeIcon icon={faCircleCheck} className="warning-check-icon" /> Paired with your device via Bluetooth</li>
                <li><FontAwesomeIcon icon={faCircleCheck} className="warning-check-icon" /> Turned ON and placed on your head correctly</li>
                <li><FontAwesomeIcon icon={faVolumeHigh} className="warning-check-icon" /> Sound is turned ON (you will hear countdown beeps)</li>
            </ul>
            <p className="warning-card-note">
                The device connection will be verified after sign in.
                Need help? <button className="warning-help-link" onClick={() => navigate('/help')}>View setup guide →</button>
            </p>
        </div>
    );
};

export default WarningComponent;
