import React from "react";
import loginService from "../service/loginService";
import { Link } from "react-router-dom";
import { useNavigate } from "react-router-dom";

const Header = () => {
    const navigate = useNavigate();

    const loggedInUser = sessionStorage.getItem('loggedInUser');
    const handleLogout = () => {
        loginService.logout();
        navigate('/login');
    }
    return (
        <header className="app-header">
            <div className="header-background">
                <div className="header-gradient"></div>
                <div className="header-pattern"></div>
            </div>

            <div className="header-content">
                <div className="header-logo">
                    <div className="brain-icon">
                        <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                            <path className="brain-left" d="M30,50 Q20,30 30,20 Q40,10 50,20 Q45,30 40,40 Q35,45 30,50" />
                            <path className="brain-right" d="M70,50 Q80,30 70,20 Q60,10 50,20 Q55,30 60,40 Q65,45 70,50" />
                            <path className="brain-center" d="M30,50 Q35,60 40,65 Q45,70 50,70 Q55,70 60,65 Q65,60 70,50" />
                            <circle className="brain-pulse" cx="50" cy="45" r="3" />
                        </svg>
                    </div>
                    <div className="logo-text">
                        <h1>BrainLink Analyzer</h1>
                        <div className="logo-tagline">Neural Analytics Suite</div>
                    </div>
                </div>

                <div className="header-badges">
                    <div className="badge">
                        <span className="badge-text">Real-time</span>
                    </div>
                    <div className="badge">
                        <span className="badge-text">Scientific</span>
                    </div>
                    <div className="badge">
                        <span className="badge-text">Brainwave Reading</span>
                    </div>
                    {loggedInUser && <Link className="logout-link" onClick={handleLogout}>Logout</Link>}
                </div>
            </div>
        </header>
    );
}

export default Header;