import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import Header from '../components/header';
import Footer from '../components/footer';
import LoginFormComponent from '../components/loginFormComponent';
import PartnerIdComponent from '../components/partnerIdComponent';
import WarningComponent from '../components/region/warningComponent';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faArrowLeft } from '@fortawesome/free-solid-svg-icons';
import '../styles/loginpage.css';

const LoginPage = () => {
    const navigate = useNavigate();
    const { t } = useTranslation();
    const [loggedInUser, setLoggedInUser] = useState(sessionStorage.getItem('loggedInUser'));

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

                    <div className="page-header">
                        {!loggedInUser && (<>
                            <h1 className="page-title">{t('login.title')}</h1>
                            <p className="page-subtitle">{t('login.subtitle')}</p>
                        </>)}
                        {loggedInUser && (<>
                            <h1 className="page-title">{t('login.partnerTitle')}</h1>
                            <p className="page-subtitle">{t('login.partnerSubtitle')}</p>
                        </>)}
                    </div>

                    {!loggedInUser && <LoginFormComponent onLoginSuccess={handleLoginSuccess} />}
                    {!loggedInUser && <WarningComponent />}
                    {loggedInUser && <PartnerIdComponent />}

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
