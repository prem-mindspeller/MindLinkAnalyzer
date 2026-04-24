import React from "react";
import loginService from "../service/loginService";
import { Link } from "react-router-dom";
import { useNavigate, useLocation } from "react-router-dom";
import StepInfoPopup from "./StepInfoPopup";
import { useTranslation } from "react-i18next";

const Header = () => {
    const navigate = useNavigate();
    const location = useLocation();
    const { t, i18n } = useTranslation();

    const loggedInUser = sessionStorage.getItem('loggedInUser');
    const handleLogout = () => {
        loginService.logout();
        navigate('/login');
    };

    const handleLanguageChange = (e) => {
        const lang = e.target.value;
        i18n.changeLanguage(lang);
        sessionStorage.setItem('language', lang);
    };
    return (
        <header className="app-header">
            <div className="header-background">
                <div className="header-gradient"></div>
                <div className="header-pattern"></div>
            </div>

            <div className="header-content">
                <div className="header-logo">
                    <img src={require("../assets/logo-with-text.png")} alt="Mindspeller Logo" className="header-logo-img" />
                </div>
                <div className="header-badges">
                    <StepInfoPopup />
                    <div className="badge">
                        <Link className="badge-text header-link" to="/help">{t('header.help')}</Link>
                    </div>
                    <div className="badge language-badge">
                        <select
                            className="language-select"
                            value={i18n.language}
                            onChange={handleLanguageChange}
                        >
                            <option value="en">English</option>
                            <option value="nl">Nederlands</option>
                        </select>
                        <span className="language-chevron">▾</span>
                    </div>
                </div>
                {loggedInUser && <Link className="logout-link" onClick={handleLogout}>{t('header.logout')}</Link>}
            </div>
        </header>
    );
}

export default Header;