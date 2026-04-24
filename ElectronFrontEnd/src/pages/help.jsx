import React, { useState } from "react";
import { useTranslation, Trans } from 'react-i18next';
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
import imgOnOff from "../assets/onoffinstructions.jpg";
import imgWearing from "../assets/wearinstructions.jpg";
import imgTakeOff from "../assets/takeoffinstructions.jpg";
import imgInsert from "../assets/insertinstructions.jpg";

const buildSections = (t) => [
    {
        id: "power",
        icon: faPowerOff,
        title: t('gettingStarted.power.title'),
        img: imgOnOff,
        content: (
            <>
                <p><strong>{t('gettingStarted.power.onLabel')}</strong></p>
                <ul>
                    <li><Trans i18nKey="gettingStarted.power.on1">Press and hold the power button for <strong>2 seconds</strong>.</Trans></li>
                    <li><Trans i18nKey="gettingStarted.power.on2">The amplifier will <strong>vibrate once</strong> to confirm it is powered on.</Trans></li>
                </ul>
                <p className="help-p-gap"><strong>{t('gettingStarted.power.offLabel')}</strong></p>
                <ul>
                    <li><Trans i18nKey="gettingStarted.power.off1">Press the power button <strong>once</strong> (short press).</Trans></li>
                    <li><Trans i18nKey="gettingStarted.power.off2">The amplifier will <strong>vibrate twice</strong> to confirm it is powered off.</Trans></li>
                </ul>
                <p className="help-p-gap"><strong>{t('gettingStarted.power.batLabel')}</strong></p>
                <ul>
                    <li><Trans i18nKey="gettingStarted.power.bat1">When the battery is empty, the amplifier will <strong>vibrate multiple times continuously</strong> and turn off automatically.</Trans></li>
                    <li>{t('gettingStarted.power.bat2')}</li>
                </ul>
            </>
        ),
    },
    {
        id: "bluetooth",
        icon: faWifi,
        title: t('gettingStarted.bluetooth.title'),
        content: (
            <>
                <p><strong>{t('gettingStarted.bluetooth.importantLabel')}</strong> {t('gettingStarted.bluetooth.introText')}</p>
                <ol className="help-list-gap">
                    <li>{t('gettingStarted.bluetooth.step1')}</li>
                    <li><Trans i18nKey="gettingStarted.bluetooth.step2">Open <strong>Settings &rarr; Bluetooth &amp; devices &rarr; Add device</strong> in Windows.</Trans></li>
                    <li><Trans i18nKey="gettingStarted.bluetooth.step3">Select <strong>&quot;Bluetooth&quot;</strong> from the add-device options.</Trans></li>
                    <li><Trans i18nKey="gettingStarted.bluetooth.step4">Wait for <strong>&quot;Brainlink_Pro (Audio)&quot;</strong> to appear in the list.</Trans></li>
                    <li><Trans i18nKey="gettingStarted.bluetooth.step5">Click on <strong>&quot;Brainlink_Pro (Audio)&quot;</strong> to pair.</Trans></li>
                </ol>
                <p className="help-note help-note--blue">
                    <Trans i18nKey="gettingStarted.bluetooth.note"><strong>Note:</strong> The headset will <strong>briefly connect and then disconnect</strong> automatically &mdash; this is normal! The pairing process only registers the headset with your device. The actual connection will be established automatically when you sign in to the application.</Trans>
                </p>
            </>
        ),
    },
    {
        id: "wearing",
        icon: faHeadset,
        title: t('gettingStarted.wearing.title'),
        img: imgWearing,
        content: (
            <>
                <ul>
                    <li><Trans i18nKey="gettingStarted.wearing.amp"><strong>Amplifier Position:</strong> Place the amplifier <strong>above your left ear</strong>.</Trans></li>
                    <li className="help-li-gap"><Trans i18nKey="gettingStarted.wearing.light"><strong>Light Sensor Position:</strong> The light sensor should be positioned <strong>right between your eyebrows</strong>.</Trans></li>
                    <li className="help-li-gap"><Trans i18nKey="gettingStarted.wearing.electrode"><strong>Electrode Position:</strong> The electrodes should be positioned <strong>2 inches above your eyebrows</strong> for optimal signal quality.</Trans></li>
                </ul>
                <p className="help-note help-note--green">
                    <Trans i18nKey="gettingStarted.wearing.tip"><strong>Tip:</strong> Proper positioning ensures accurate EEG readings. Take a moment to adjust the headset before starting calibration.</Trans>
                </p>
            </>
        ),
    },
    {
        id: "charging",
        icon: faBatteryEmpty,
        title: t('gettingStarted.charging.title'),
        img: imgTakeOff,
        content: (
            <>
                <p>{t('gettingStarted.charging.intro')}</p>
                <ol className="help-list-gap">
                    <li>{t('gettingStarted.charging.step1')}</li>
                    <li><Trans i18nKey="gettingStarted.charging.step2">Gently pull the amplifier <strong>out of the clip</strong>.</Trans></li>
                    <li>{t('gettingStarted.charging.step3')}</li>
                    <li>{t('gettingStarted.charging.step4')}</li>
                </ol>
                <p className="help-note help-note--yellow">
                    <Trans i18nKey="gettingStarted.charging.note"><strong>Note:</strong> The amplifier cannot be charged while attached to the headset clip.</Trans>
                </p>
            </>
        ),
    },
    {
        id: "reinsert",
        icon: faPlug,
        title: t('gettingStarted.reinsert.title'),
        img: imgInsert,
        content: (
            <>
                <p>{t('gettingStarted.reinsert.intro')}</p>
                <ol className="help-list-gap">
                    <li>{t('gettingStarted.reinsert.step1')}</li>
                    <li>{t('gettingStarted.reinsert.step2')}</li>
                    <li><Trans i18nKey="gettingStarted.reinsert.step3">Gently push the amplifier into the clip until it <strong>clicks securely</strong>.</Trans></li>
                    <li>{t('gettingStarted.reinsert.step4')}</li>
                </ol>
                <p className="help-note help-note--green">
                    <Trans i18nKey="gettingStarted.reinsert.note"><strong>Important:</strong> Make sure the amplifier is properly seated to maintain good electrode contact.</Trans>
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
