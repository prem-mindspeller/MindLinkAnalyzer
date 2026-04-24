import React, { useState } from "react";
import { useTranslation } from 'react-i18next';
import loginService from '../service/loginService';
import wsEegService from '../service/wsEegService';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faXmark, faEye, faEyeSlash, faTriangleExclamation, faSpinner } from '@fortawesome/free-solid-svg-icons';

const LoginFormComponent = ({ onLoginSuccess }) => {
    const { t } = useTranslation();
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [showPassword, setShowPassword] = useState(false);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState('');

    const handleSubmit = async (e) => {
        e.preventDefault();
        setIsLoading(true);
        setError('');

        const region = sessionStorage.getItem('region') || 'en';

        try {
            const result = await loginService.loginUser(email, password, region);

            if (result.success) {
                console.log('Login successful');
                wsEegService.init();
                onLoginSuccess(email);
            } else {
                setError(result.error || t('loginForm.errorFailed'));
            }
        } catch (err) {
            console.error('Login exception:', err);
            setError(t('loginForm.errorGeneral'));
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="login-card">
            <form onSubmit={handleSubmit} className="login-form">
                <div className="form-group">
                    <label className="input-label">
                        <span className="label-text">{t('loginForm.emailLabel')}</span>
                        <span className="label-required">*</span>
                    </label>
                    <div className="input-wrapper">
                        <input
                            type="email"
                            className="form-input"
                            placeholder={t('loginForm.emailPlaceholder')}
                            value={email}
                            onChange={(e) => {
                                setEmail(e.target.value);
                                setError('');
                            }}
                            required
                        />
                        {email && (
                            <button
                                type="button"
                                className="clear-btn"
                                onClick={() => setEmail('')}
                            >
                                <FontAwesomeIcon icon={faXmark} />
                            </button>
                        )}
                    </div>
                </div>

                <div className="form-group">
                    <label className="input-label">
                        <span className="label-text">{t('loginForm.passwordLabel')}</span>
                        <span className="label-required">*</span>
                    </label>
                    <div className="input-wrapper">
                        <input
                            type={showPassword ? 'text' : 'password'}
                            className="form-input"
                            placeholder={t('loginForm.passwordPlaceholder')}
                            value={password}
                            onChange={(e) => {
                                setPassword(e.target.value);
                                setError('');
                            }}
                            required
                        />
                        <button
                            type="button"
                            className="toggle-password-btn"
                            onClick={() => setShowPassword(!showPassword)}
                        >
                            <FontAwesomeIcon icon={showPassword ? faEyeSlash : faEye} />
                        </button>
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
                            {t('loginForm.signingIn')}
                        </>
                    ) : (
                        <span>{t('loginForm.signIn')}</span>
                    )}
                </button>
            </form>
        </div>
    );
}

export default LoginFormComponent;