import React, { useState, useEffect } from 'react';

const RegionSelectionCard = () => {
    const [selectedRegion, setSelectedRegion] = useState(() => {
        return sessionStorage.getItem('region') || 'en';
    });

    const regions = [
        { value: 'en', label: 'English (en)', url: 'en.mindspeller.com' },
        { value: 'nl', label: 'Nederlands (nl)', url: 'stg-nl.mindspell.be' },
        { value: 'local', label: 'Local', url: '127.0.0.1:5000' }
    ];

    useEffect(() => {
        // Save region to sessionStorage whenever it changes
        sessionStorage.setItem('region', selectedRegion);
    }, [selectedRegion]);

    return (
        <div className="content-card">
            <label className="input-label">
                <span className="label-text">Region:</span>
                <span className="label-required">*</span>
            </label>

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
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                        <path d="M5 7.5L10 12.5L15 7.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                </span>
            </div>


            <div className="warning-box">
                <div className="warning-icon">⚠️</div>
                <div className="warning-content">
                    <strong>Important:</strong> Please make sure the region selected is the region where the user has created their Mindspeller account
                </div>
            </div>
        </div>
    );
}

export default RegionSelectionCard;