import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Footer from '../components/footer';
import '../styles/pathway.css';

const PathwayPage = () => {
    const navigate = useNavigate();
    const [battery] = useState(95);
    const [selectedPathway, setSelectedPathway] = useState('connection');

    const pathways = [
        {
            id: 'personal',
            title: 'Personal Pathway',
            description: 'Career Flow related tasks',
        },
        {
            id: 'connection',
            title: 'Connection',
            description: 'Mind Flow related tasks',
        },
        {
            id: 'lifestyle',
            title: 'Lifestyle',
            description: 'Style Flow related tasks',
        }
    ];

    const handleBack = () => {
        navigate(-1);
    };

    const handleNext = () => {
        console.log('Selected pathway:', selectedPathway);
    };

    const handleHelp = () => {
        console.log('Help clicked');
    };

    return (
        <div className="app-container">
            <header className="pathway-header">
                <div className="header-left">
                    <div className="battery-indicator">
                        <span className="battery-label">Battery</span>
                        <div className="battery-bar-container">
                            <div
                                className="battery-bar"
                                style={{ width: `${battery}%` }}
                            ></div>
                        </div>
                        <span className="battery-percentage">{battery}%</span>
                    </div>
                </div>

                <div className="header-center">
                    <div className="status-item">
                        <span className="status-label">EEG:</span>
                        <span className="status-icon warning">⚠</span>
                        <span className="status-value warning-text">Not Worn</span>
                    </div>
                    <div className="status-divider">|</div>
                    <div className="status-item">
                        <span className="status-label">Signal:</span>
                        <span className="status-icon warning">⚠</span>
                        <span className="status-value warning-text">Headset</span>
                    </div>
                </div>

                <div className="header-right">
                    <button className="help-btn" onClick={handleHelp}>
                        <span className="help-icon">❓</span>
                        Help
                    </button>
                </div>
            </header>

            <main className="app-main">
                <div className="pathway-page">
                    <div className="page-header-pathway">
                        <h1 className="page-title-pathway">Choose Your Pathway</h1>
                        <p className="step-indicator-pathway">Select the flow type to tailor your task list</p>
                    </div>


                    <div className="protocol-card">
                        <h2 className="protocol-title">Select Protocol:</h2>

                        <div className="pathways-container">
                            {pathways.map((pathway) => (
                                <label
                                    key={pathway.id}
                                    className={`pathway-option ${selectedPathway === pathway.id ? 'selected' : ''}`}
                                >
                                    <input
                                        type="radio"
                                        name="pathway"
                                        value={pathway.id}
                                        checked={selectedPathway === pathway.id}
                                        onChange={(e) => setSelectedPathway(e.target.value)}
                                        className="pathway-radio"
                                    />
                                    <div className="pathway-content">
                                        <div className="pathway-header">
                                            <span className="pathway-icon">{pathway.icon}</span>
                                            <span className="pathway-title">{pathway.title}</span>
                                            <div className="radio-indicator"></div>
                                        </div>
                                        <p className="pathway-description">{pathway.description}</p>
                                    </div>
                                </label>
                            ))}
                        </div>
                    </div>


                    <div className="info-box-pathway">
                        <span className="info-text-pathway">
                            Baseline calibration and core cognitive tasks are included in all pathways
                        </span>
                    </div>

                    <div className="navigation-buttons-pathway">
                        <button className="btn-back-pathway" onClick={handleBack}>
                            ← Back
                        </button>
                        <button className="btn-next-pathway" onClick={handleNext}>
                            Next →
                        </button>
                    </div>
                </div>
            </main>
            <Footer />
        </div>
    );
};

export default PathwayPage;