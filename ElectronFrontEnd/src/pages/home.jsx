import React from "react";
import { useNavigate } from "react-router-dom";
import Header from "../components/header";
import Footer from "../components/footer";
import StepsComponent from "../components/region/stepsComponent";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
    faBrain, faChartLine, faShieldHalved, faArrowRight, faHeadset,
} from "@fortawesome/free-solid-svg-icons";
import "../styles/home.css";

const FEATURES = [
    {
        icon: faBrain,
        title: "Real-Time EEG Recording",
        description: "Capture live brainwave data from your EEG headset with millisecond precision.",
    },
    {
        icon: faChartLine,
        title: "Cognitive Task Analysis",
        description: "Run validated cognitive tasks and receive a statistical analysis of your brain activity across frequency bands.",
    },
    {
        icon: faHeadset,
        title: "Guided Workflow",
        description: "A step-by-step process walks you through device setup, baseline calibration, tasks, and results — no expertise needed.",
    },
    {
        icon: faShieldHalved,
        title: "Data Sovereignty",
        description: "Choose your regional server so your neurological data stays within your preferred jurisdiction.",
    },
];

const HomePage = () => {
    const navigate = useNavigate();

    return (
        <div className="app-container">
            <Header />
            <main className="app-main home-main">

                {/* ── Hero ── */}
                <section className="home-hero">
                    <div className="home-hero-text">
                        <p className="home-hero-eyebrow">Mindspeller · MindLink Analyzer</p>
                        <h1 className="home-hero-title">
                            Understand your brain.<br />
                            <span className="home-hero-accent">One session at a time.</span>
                        </h1>
                        <p className="home-hero-subtitle">
                            MindLink Analyzer records your EEG activity during a series of cognitive tasks,
                            compares it against your personal baseline, and generates a detailed neural
                            profile — all from a consumer-grade headset.
                        </p>
                        <div className="home-hero-actions">
                            <button className="home-btn-primary" onClick={() => navigate("/region")}>
                                Get Started <FontAwesomeIcon icon={faArrowRight} style={{ marginLeft: 8 }} />
                            </button>
                            <button className="home-btn-secondary" onClick={() => navigate("/help")}>
                                How it works
                            </button>
                        </div>
                    </div>
                </section>

                {/* ── Features ── */}
                <section className="home-features">
                    <h2 className="home-section-title">What MindLink Analyzer does</h2>
                    <div className="home-feature-grid">
                        {FEATURES.map((f) => (
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
                    <h2 className="home-section-title">Your session at a glance</h2>
                    <p className="home-section-subtitle">
                        A complete session takes around 20–30 minutes and is fully guided.
                    </p>
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
