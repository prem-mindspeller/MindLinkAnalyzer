import React from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import Header from "../components/header";
import Footer from "../components/footer";
import StepsComponent from "../components/region/stepsComponent";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
    faBrain, faChartLine, faShieldHalved, faArrowRight, faHeadset,
} from "@fortawesome/free-solid-svg-icons";
import "../styles/home.css";

const FEATURES = (t) => [
    {
        icon: faBrain,
        title: t('home.feature1Title'),
        description: t('home.feature1Desc'),
    },
    {
        icon: faChartLine,
        title: t('home.feature2Title'),
        description: t('home.feature2Desc'),
    },
    {
        icon: faHeadset,
        title: t('home.feature3Title'),
        description: t('home.feature3Desc'),
    },
    {
        icon: faShieldHalved,
        title: t('home.feature4Title'),
        description: t('home.feature4Desc'),
    },
];

const HomePage = () => {
    const navigate = useNavigate();
    const { t } = useTranslation();

    return (
        <div className="app-container">
            <Header />
            <main className="app-main home-main">

                {/* ── Hero ── */}
                <section className="home-hero">
                    <div className="home-hero-text">
                        <p className="home-hero-eyebrow">{t('home.eyebrow')}</p>
                        <h1 className="home-hero-title">
                            {t('home.title')}<br />
                            <span className="home-hero-accent">{t('home.titleAccent')}</span>
                        </h1>
                        <p className="home-hero-subtitle">{t('home.subtitle')}</p>
                        <div className="home-hero-actions">
                            <button className="home-btn-primary" onClick={() => navigate("/region")}>
                                {t('home.getStarted')} <FontAwesomeIcon icon={faArrowRight} style={{ marginLeft: 8 }} />
                            </button>
                            <button className="home-btn-secondary" onClick={() => navigate("/help")}>
                                {t('home.howItWorks')}
                            </button>
                        </div>
                    </div>
                </section>

                {/* ── Features ── */}
                <section className="home-features">
                    <h2 className="home-section-title">{t('home.featuresTitle')}</h2>
                    <div className="home-feature-grid">
                        {FEATURES(t).map((f) => (
                            <div key={f.title} className="home-feature-card">
                                <div className="home-feature-icon">
                                    <FontAwesomeIcon icon={f.icon} />
                                </div>
                                <h3 className="home-feature-name">{f.title}</h3>
                                <p className="home-feature-desc">{f.description}</p>
                            </div>
                        ))}
                    </div>
                </section>

                {/* ── Steps ── */}
                <section className="home-steps-section">
                    <h2 className="home-section-title">{t('home.stepsTitle')}</h2>
                    <p className="home-section-subtitle">{t('home.stepsSubtitle')}</p>
                    <div className="home-steps-wrap">
                        <StepsComponent currentStep={0} />
                    </div>
                </section>

            </main>
            <Footer />
        </div>
    );
};

export default HomePage;
