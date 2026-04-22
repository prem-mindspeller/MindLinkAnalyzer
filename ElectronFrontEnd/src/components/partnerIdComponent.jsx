import React, { useState } from "react";
import { useNavigate } from 'react-router-dom';
import loginService from '../service/loginService';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faXmark, faTriangleExclamation, faArrowRight, faSpinner } from '@fortawesome/free-solid-svg-icons';

const PartnerIdComponent = () => {
    const [id, setId] = useState(localStorage.getItem('partnerId') || sessionStorage.getItem('partnerId') || '');
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState('');
    const navigate = useNavigate();

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setIsLoading(true);

        const trimmedId = id.trim();
        const result = await loginService.checkPartnerBookings(trimmedId);

        if (result.notFound) {
            setError(`Partner ID "${trimmedId}" is not recognised. Please check and try again.`);
            setIsLoading(false);
            return;
        }

        if (!result.success) {
            setError('Could not verify Partner ID. Please check your connection and try again.');
            setIsLoading(false);
            return;
        }

        sessionStorage.setItem('partnerId', trimmedId);
        localStorage.setItem('partnerId', trimmedId);
        sessionStorage.setItem('hasAdvancedBooking', result.hasAdvancedBooking ? 'true' : 'false');

        setIsLoading(false);
        navigate('/liveReading');
    };

    return (
        <div className="login-card">
            <form onSubmit={handleSubmit} className="login-form">
                <div className="form-group">
                    <label className="input-label">
                        <span className="label-text">Partner ID:</span>
                        <span className="label-required">*</span>
                    </label>
                    <div className="input-wrapper">
                        <input
                            type="text"
                            className="form-input"
                            placeholder="Enter your Partner ID"
                            value={id}
                            onChange={(e) => { setId(e.target.value); setError(''); }}
                            required
                        />
                        {id && (
                            <button
                                type="button"
                                className="clear-btn"
                                onClick={() => setId('')}
                            >
                                <FontAwesomeIcon icon={faXmark} />
                            </button>
                        )}
                    </div>
                </div>

                {error && (
                    <div className="error-message">
                        <span className="error-icon"><FontAwesomeIcon icon={faTriangleExclamation} /></span>
                        <span>{error}</span>
                    </div>
                )}

                <button
                    type="submit"
                    className={`submit-btn ${isLoading ? 'loading' : ''}`}
                    disabled={isLoading}
                >
                    {isLoading ? (
                        <>
                            <FontAwesomeIcon icon={faSpinner} spin style={{ marginRight: 8 }} />
                            Submitting...
                        </>
                    ) : (
                        <>
                            <span>Submit Partner ID</span>
                            <FontAwesomeIcon icon={faArrowRight} style={{ marginLeft: 8 }} />
                        </>
                    )}
                </button>
            </form>
        </div>
    );
}
export default PartnerIdComponent;