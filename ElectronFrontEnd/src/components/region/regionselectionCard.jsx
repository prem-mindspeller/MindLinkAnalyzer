import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';

const RegionSelectionCard = () => {
    const [selectedRegion, setSelectedRegion] = useState(() => {
        return sessionStorage.getItem('region') || 'en';
    });

    const regions = [
        { value: 'en', label: 'English (en)', url: 'en.mindspeller.com' }
    ];

    useEffect(() => {
        sessionStorage.setItem('region', selectedRegion);
    }, [selectedRegion]);

    return (
        <div className="region-card">
            {/* Left panel */}
            <div className="region-card-left">
                <div className="globe-icon-wrapper">
                    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <circle cx="12" cy="12" r="9" stroke="#6c63ff" strokeWidth="1.8" />
                        <ellipse cx="12" cy="12" rx="4" ry="9" stroke="#6c63ff" strokeWidth="1.8" />
                        <path d="M3 12h18" stroke="#6c63ff" strokeWidth="1.8" strokeLinecap="round" />
                        <path d="M3.6 8h16.8M3.6 16h16.8" stroke="#6c63ff" strokeWidth="1.4" strokeLinecap="round" />
                    </svg>
                </div>
                <div className="region-label-group">
                    <h3 className="region-identity-title">Region</h3>
                    <p className="region-identity-sub">Data Sovereignty</p>
                </div>
            </div>

            {/* Right panel */}
            <div className="region-card-right">
                <div className="select-wrapper">
                    <select
                        className="region-select"
                        value={selectedRegion}
                        onChange={(e) => setSelectedRegion(e.target.value)}
                    >
                        {regions.map(region => (
                            <option key={region.value} value={region.value}>
                                {region.label}
                            </option>
                        ))}
                    </select>
                    <span className="select-icon">
                        <svg width="18" height="18" viewBox="0 0 20 20" fill="none">
                            <path d="M5 7.5L10 12.5L15 7.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                    </span>
                </div>

                <div className="region-info-box">
                    <div className="info-circle">i</div>
                    <div className="region-info-text">
                        <strong>Important Notice</strong>
                        <p>Before continuing, make sure your device is paired with your EEG headset via Bluetooth and that you have an existing account on the website. Consult the <Link to="/help">help menu</Link> in the top right corner for guidance.</p>
                    </div>
                </div>
            </div>
        </div>
    );
}

export default RegionSelectionCard;