import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import Header from '../components/header';
import Footer from '../components/footer';
import LoginFormComponent from '../components/loginFormComponent';
import PartnerIdComponent from '../components/partnerIdComponent';
import WarningComponent from '../components/region/warningComponent';
import QrSignInComponent from '../components/QrSignInComponent';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faArrowLeft, faQrcode } from '@fortawesome/free-solid-svg-icons';
import '../styles/loginpage.css';

const LoginPage = () => {
    const navigate = useNavigate();
    const { t } = useTranslation();
    const [loggedInUser, setLoggedInUser] = useState(sessionStorage.getItem('loggedInUser'));
    const [mode, setMode] = useState('password');

    const handleBack = () => {
        navigate('/region');
    };

    const handleLoginSuccess = (email) => {
        sessionStorage.setItem('loggedInUser', email);
        setLoggedInUser(email);
    };

    return (
        <div className="app-container">
            <Header />
            <main className="app-main">
                <div className="login-page">

                    <section className="login-panel">
                        <div className="page-header">
                            {!loggedInUser && (<>
                                <h1 className="page-title">{t('login.title')}</h1>
                                <p className="page-subtitle">
                                    {mode === 'qr' ? t('qrSignIn.subtitle') : t('login.subtitle')}
                                </p>
                            </>)}
                            {loggedInUser && (<>
                                <h1 className="page-title">{t('login.partnerTitle')}</h1>
                                <p className="page-subtitle">{t('login.partnerSubtitle')}</p>
                            </>)}
                        </div>

                        {!loggedInUser && mode === 'password' && (
                            <>
                                <LoginFormComponent onLoginSuccess={handleLoginSuccess} />
                                <div className="login-alt-group">
                                    <div className="login-alt">
                                        <span className="login-alt-line"></span>
                                        <span className="login-alt-text">{t('qrSignIn.or')}</span>
                                        <span className="login-alt-line"></span>
                                    </div>
                                    <button
                                        type="button"
                                        className="qr-switch-btn"
                                        onClick={() => setMode('qr')}
                                    >
                                        <FontAwesomeIcon icon={faQrcode} style={{ marginRight: 8 }} />
                                        {t('qrSignIn.switchCta')}
                                    </button>
                                </div>
                            </>
                        )}

                        {!loggedInUser && mode === 'qr' && (
                            <QrSignInComponent
                                onLoginSuccess={handleLoginSuccess}
                                onCancel={() => setMode('password')}
                            />
                        )}

                        {loggedInUser && <PartnerIdComponent />}
                    </section>

                    {!loggedInUser && <WarningComponent />}

                </div>
            </main>
            <div className="nav-sub-footer">
                <button className="btn-back" onClick={handleBack}>
                    <FontAwesomeIcon icon={faArrowLeft} style={{ marginRight: 6 }} />{t('nav.back')}
                </button>
            </div>
            <Footer />
        </div>
    );
}

export default LoginPage;
