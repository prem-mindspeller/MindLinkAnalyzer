import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
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
                            <h1 className="page-title">Sign In</h1>
                            <p className="page-subtitle">Step 2 of 7: Enter your Mindspeller account credentials to continue</p>
                        </>)}
                        {loggedInUser && (<>
                            <h1 className="page-title">Enter Partner ID</h1>
                            <p className="page-subtitle">Step 3 of 7: Enter your Partner ID to proceed</p>
                        </>)}
                    </div>

                    {!loggedInUser && <LoginFormComponent onLoginSuccess={handleLoginSuccess} />}
                    {!loggedInUser && <WarningComponent />}
                    {loggedInUser && <PartnerIdComponent />}

                    <div className="navigation-buttons2">
                        <button className="btn-back" onClick={handleBack}>
                            <FontAwesomeIcon icon={faArrowLeft} style={{ marginRight: 6 }} />Back
                        </button>
                    </div>
                </div>
            </main>
            <Footer />
        </div>
    );
}

export default LoginPage;
