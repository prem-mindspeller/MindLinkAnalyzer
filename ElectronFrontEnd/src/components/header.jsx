import React from "react";
import loginService from "../service/loginService";
import { Link } from "react-router-dom";
import { useNavigate, useLocation } from "react-router-dom";
import StepInfoPopup from "./StepInfoPopup";
import { useTranslation } from "react-i18next";
import LanguageMenu from "./LanguageMenu";

const Header = () => {
    const navigate = useNavigate();
    const location = useLocation();
    const { t } = useTranslation();

    const loggedInUser = sessionStorage.getItem('loggedInUser');
    const handleLogout = () => {
        loginService.logout();
        navigate('/login');
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
                    <LanguageMenu />
                </div>
                {loggedInUser && <Link className="logout-link" onClick={handleLogout}>{t('header.logout')}</Link>}
            </div>
        </header>
    );
}

export default Header;
