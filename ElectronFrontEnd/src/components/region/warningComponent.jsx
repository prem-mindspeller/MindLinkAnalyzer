import React from 'react';

const WarningComponent = () => {
    return (
        <>
                        <div className="content-card info-card">
                            <h3 className="card-title">Before You Continue:</h3><div className="instruction-box">
                                <div className="instruction-header">
                                    <span className="instruction-icon">ℹ️</span>
                                    <span className="instruction-title">Please ensure the headset is:</span>
                                </div>

                                <ul className="checklist">
                                    <li className="checklist-item">
                                        <span className="check-icon">✓</span>
                                        <span>Paired with your device via Bluetooth</span>
                                    </li>
                                    <li className="checklist-item">
                                        <span className="check-icon">✓</span>
                                        <span>Turned ON and placed on your head correctly</span>
                                    </li>
                                </ul>

                                <p className="instruction-note">
                                    The device connection will be verified when you sign in on the next step.
                                </p>
                            </div><button className="help-button">
                                    <span className="help-icon">❓</span>
                                    Setup Help
                                </button>
                        </div>
        </>

    )
}

export default WarningComponent;