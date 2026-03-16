import React, { useState } from "react";
import loginService from '../service/loginService';

const LoginFormComponent = ({ onLoginSuccess }) => {
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
                onLoginSuccess(email);
            } else {
                setError(result.error || 'Login failed. Please check your credentials.');
            }
        } catch (err) {
            console.error('Login exception:', err);
            setError('An error occurred during login. Please try again.');
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="login-card">
            <form onSubmit={handleSubmit} className="login-form">
                <div className="form-group">
                    <label className="input-label">
                        <span className="label-text">Email:</span>
                        <span className="label-required">*</span>
                    </label>
                    <div className="input-wrapper">
                        <input
                            type="email"
                            className="form-input"
                            placeholder="Enter your email"
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
                                ✕
                            </button>
                        )}
                    </div>
                </div>

                <div className="form-group">
                    <label className="input-label">
                        <span className="label-text">Password:</span>
                        <span className="label-required">*</span>
                    </label>
                    <div className="input-wrapper">
                        <input
                            type={showPassword ? 'text' : 'password'}
                            className="form-input"
                            placeholder="Enter your password"
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
                            {showPassword ? '👁️' : '👁️‍🗨️'}
                        </button>
                    </div>
                </div>

                {error && (
                    <div className="error-message">
                        <span className="error-icon">⚠️</span>
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
                            <span className="spinner"></span>
                            Signing in...
                        </>
                    ) : (
                        <>
                            <span>Sign In</span>
                        </>
                    )}
                </button>
            </form>
        </div>
    );
}

export default LoginFormComponent;