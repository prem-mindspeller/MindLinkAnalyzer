import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Header from '../components/header';
import Footer from '../components/footer';
import LoginFormComponent from '../components/loginFormComponent';
import PartnerIdComponent from '../components/partnerIdComponent';
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
                        <h1 className="page-title">Sign In</h1>
                        <p className="page-subtitle">Enter your credentials to continue</p>
                    </div>
                    {!loggedInUser && <LoginFormComponent onLoginSuccess={handleLoginSuccess} />}
                    {loggedInUser && <PartnerIdComponent />}

                    <div className="navigation-buttons">
                        <button className="btn-back" onClick={handleBack}>
                            ← Back
                        </button>
                    </div>
                </div>
            </main>
            <Footer />
        </div>
    );
}

export default LoginPage;
