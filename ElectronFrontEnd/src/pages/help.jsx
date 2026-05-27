import React, { useState } from "react";
import { useTranslation } from 'react-i18next';
import Header from "../components/header";
import Footer from "../components/footer";
import { useNavigate } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
    faArrowLeft, faPowerOff, faWifi, faHeadset,
    faBatteryEmpty, faPlug, faBookOpen, faRocket, faLightbulb,
} from "@fortawesome/free-solid-svg-icons";
import "../styles/regionpage.css";
import "../styles/help.css";

const buildSections = (t) => [
    {
        id: "power",
        icon: faPowerOff,
        title: t('gettingStarted.power.title'),
        content: (
            <>
                <p><strong>{t('gettingStarted.power.onLabel')}</strong></p>
                <ul>
                    <li>{t('gettingStarted.power.on1')}</li>
                    <li>{t('gettingStarted.power.on2')}</li>
                </ul>
                <p className="help-p-gap"><strong>{t('gettingStarted.power.offLabel')}</strong></p>
                <ul>
                    <li>{t('gettingStarted.power.off1')}</li>
                </ul>
                <p className="help-p-gap"><strong>{t('gettingStarted.power.batLabel')}</strong></p>
                <ul>
                    <li>{t('gettingStarted.power.bat1')}</li>
                    <li>{t('gettingStarted.power.bat2')}</li>
                </ul>
            </>
        ),
    },
    {
        id: "wifi",
        icon: faWifi,
        title: t('gettingStarted.wifi.title'),
        content: (
            <>
                <p>{t('gettingStarted.wifi.intro')}</p>
                <ol className="help-list-gap">
                    <li>{t('gettingStarted.wifi.step1')}</li>
                    <li>{t('gettingStarted.wifi.step2')}</li>
                    <li>{t('gettingStarted.wifi.step3')}</li>
                    <li>{t('gettingStarted.wifi.step4')}</li>
                </ol>
                <p className="help-note help-note--blue">
                    <strong>{t('gettingStarted.wifi.noteLabel')}</strong> {t('gettingStarted.wifi.noteText')}
                </p>
            </>
        ),
    },
    {
        id: "wearing",
        icon: faHeadset,
        title: t('gettingStarted.wearing.title'),
        content: (
            <>
                <ul>
                    <li><strong>{t('gettingStarted.wearing.frontLabel')}</strong> {t('gettingStarted.wearing.frontText')}</li>
                    <li className="help-li-gap"><strong>{t('gettingStarted.wearing.backLabel')}</strong> {t('gettingStarted.wearing.backText')}</li>
                    <li className="help-li-gap"><strong>{t('gettingStarted.wearing.earsLabel')}</strong> {t('gettingStarted.wearing.earsText')}</li>
                    <li className="help-li-gap">{t('gettingStarted.wearing.nogel')}</li>
                </ul>
                <p className="help-note help-note--green">
                    <strong>{t('gettingStarted.wearing.tipLabel')}</strong> {t('gettingStarted.wearing.tipText')}
                </p>
            </>
        ),
    },
    {
        id: "charging",
        icon: faBatteryEmpty,
        title: t('gettingStarted.charging.title'),
        content: (
            <>
                <p>{t('gettingStarted.charging.intro')}</p>
                <ol className="help-list-gap">
                    <li>{t('gettingStarted.charging.step1')}</li>
                    <li>{t('gettingStarted.charging.step2')}</li>
                    <li>{t('gettingStarted.charging.step3')}</li>
                </ol>
                <p className="help-note help-note--yellow">
                    <strong>{t('gettingStarted.charging.noteLabel')}</strong> {t('gettingStarted.charging.noteText')}
                </p>
            </>
        ),
    },
    {
        id: "appconnect",
        icon: faPlug,
        title: t('gettingStarted.appconnect.title'),
        content: (
            <>
                <p>{t('gettingStarted.appconnect.intro')}</p>
                <ol className="help-list-gap">
                    <li>{t('gettingStarted.appconnect.step1')}</li>
                    <li>{t('gettingStarted.appconnect.step2')}</li>
                    <li>{t('gettingStarted.appconnect.step3')}</li>
                </ol>
                <p className="help-note help-note--blue">
                    <strong>{t('gettingStarted.appconnect.tipLabel')}</strong> {t('gettingStarted.appconnect.tipText')}
                </p>
            </>
        ),
    },
];

const HelpPage = () => {
    const navigate = useNavigate();
    const { t } = useTranslation();
    const SECTIONS = buildSections(t);
    const [activeTab, setActiveTab] = useState("started");
    const [expandedSection, setExpandedSection] = useState(null);
    const [expandedManual, setExpandedManual] = useState(null);
    const [expandedTip, setExpandedTip] = useState(null);

    const toggleSection = (id) => setExpandedSection(prev => prev === id ? null : id);
    const toggleManual = (idx) => setExpandedManual(prev => prev === idx ? null : idx);
    const toggleTip = (idx) => setExpandedTip(prev => prev === idx ? null : idx);

    return (
        <div className="app-container">
            <Header />
            <main className="app-main">
                <div className="help-wrapper">

                    <div className="help-page-header">
                        <h1 className="help-page-title">{t('help.title')}</h1>
                        <p className="help-page-subtitle">{t('help.subtitle')}</p>
                    </div>

                    <div className="help-tab-bar">
                        {[
                            { id: "started", icon: faRocket, label: t('help.gettingStarted') },
                            { id: "manual", icon: faBookOpen, label: t('help.userManual') },
                            { id: "tips", icon: faLightbulb, label: t('help.tips') },
                        ].map(tab => (
                            <button
                                key={tab.id}
                                onClick={() => setActiveTab(tab.id)}
                                className={`help-tab-btn${activeTab === tab.id ? " active" : ""}`}
                            >
                                <FontAwesomeIcon icon={tab.icon} />
                                {tab.label}
                            </button>
                        ))}
                    </div>

                    {activeTab === "started" && (
                        <div className="help-accordion">
                            {SECTIONS.map(section => (
                                <div key={section.id} className="help-card">
                                    <button
                                        className="help-card-trigger"
                                        onClick={() => toggleSection(section.id)}
                                    >
                                        <span className="help-icon-badge">
                                            <FontAwesomeIcon icon={section.icon} />
                                        </span>
                                        <span className="help-card-title">{section.title}</span>
                                        <span className="help-toggle">
                                            {expandedSection === section.id ? "\u2212" : "+"}
                                        </span>
                                    </button>

                                    {expandedSection === section.id && (
                                        <div className="help-card-body">
                                            <div className="help-card-body-inner">
                                                <div className="help-card-text">{section.content}</div>
                                                {section.img && (
                                                    <div className="help-card-img-col">
                                                        <img
                                                            src={section.img}
                                                            alt={section.title}
                                                            className="help-instruction-img"
                                                        />
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    )}

                    {activeTab === "manual" && (
                        <div className="help-accordion">
                            {[0, 1, 2, 3, 4, 5, 6].map((idx) => (
                                <div key={idx} className="help-card">
                                    <button
                                        className="help-card-trigger"
                                        onClick={() => toggleManual(idx)}
                                    >
                                        <span className="help-num-badge">{idx + 1}</span>
                                        <span className="help-card-title">{t(`manual.${idx}.title`)}</span>
                                        <span className="help-toggle">
                                            {expandedManual === idx ? "\u2212" : "+"}
                                        </span>
                                    </button>

                                    {expandedManual === idx && (
                                        <div className="help-card-body--manual">
                                            {t(`manual.${idx}.content`)}
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    )}

                    {activeTab === "tips" && (
                        <div className="help-accordion">
                            {[0, 1, 2, 3, 4, 5].map((idx) => (
                                <div key={idx} className="help-card">
                                    <button
                                        className="help-card-trigger"
                                        onClick={() => toggleTip(idx)}
                                    >
                                        <span className="help-icon-badge help-icon-badge--tip">
                                            <FontAwesomeIcon icon={faLightbulb} />
                                        </span>
                                        <span className="help-card-title">{t(`tips.${idx}.title`)}</span>
                                        <span className="help-toggle">
                                            {expandedTip === idx ? "−" : "+"}
                                        </span>
                                    </button>
                                    {expandedTip === idx && (
                                        <div className="help-card-body--manual">
                                            {t(`tips.${idx}.content`)}
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    )}

                    <div className="help-back-row">
                        <button className="btn-back" onClick={() => navigate(-1)}>
                            <FontAwesomeIcon icon={faArrowLeft} /> {t('nav.back')}
                        </button>
                    </div>
                </div>
            </main>
            <Footer />
        </div>
    );
};

export default HelpPage;
