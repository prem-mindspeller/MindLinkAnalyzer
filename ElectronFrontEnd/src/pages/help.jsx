import React, { useState } from "react";
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

const SECTIONS = [
    {
        id: "power",
        icon: faPowerOff,
        title: "1. Turning the Amplifier On / Off",
        img: imgOnOff,
        content: (
            <>
                <p><strong>To Turn ON:</strong></p>
                <ul>
                    <li>Press and hold the power button for <strong>2 seconds</strong>.</li>
                    <li>The amplifier will <strong>vibrate once</strong> to confirm it is powered on.</li>
                </ul>
                <p className="help-p-gap"><strong>To Turn OFF:</strong></p>
                <ul>
                    <li>Press the power button <strong>once</strong> (short press).</li>
                    <li>The amplifier will <strong>vibrate twice</strong> to confirm it is powered off.</li>
                </ul>
                <p className="help-p-gap"><strong>Low Battery Warning:</strong></p>
                <ul>
                    <li>When the battery is empty, the amplifier will <strong>vibrate multiple times continuously</strong> and turn off automatically.</li>
                    <li>Please charge the amplifier when this happens.</li>
                </ul>
            </>
        ),
    },
    {
        id: "bluetooth",
        icon: faWifi,
        title: "2. Pairing the Amplifier with Your Device",
        content: (
            <>
                <p><strong>Important:</strong> Follow the standard Windows Bluetooth pairing process:</p>
                <ol className="help-list-gap">
                    <li>Turn on the amplifier (press and hold for 2 seconds).</li>
                    <li>Open <strong>Settings &rarr; Bluetooth &amp; devices &rarr; Add device</strong> in Windows.</li>
                    <li>Select <strong>&quot;Bluetooth&quot;</strong> from the add-device options.</li>
                    <li>Wait for <strong>&quot;Brainlink_Pro (Audio)&quot;</strong> to appear in the list.</li>
                    <li>Click on <strong>&quot;Brainlink_Pro (Audio)&quot;</strong> to pair.</li>
                </ol>
                <p className="help-note help-note--blue">
                    <strong>Note:</strong> The headset will <strong>briefly connect and then disconnect</strong> automatically &mdash; this is normal!
                    The pairing process only registers the headset with your device. The actual connection will be established automatically when you sign in to the application.
                </p>
            </>
        ),
    },
    {
        id: "wearing",
        icon: faHeadset,
        title: "3. Wearing the Headset Properly",
        img: imgWearing,
        content: (
            <>
                <ul>
                    <li><strong>Amplifier Position:</strong> Place the amplifier <strong>above your left ear</strong>.</li>
                    <li className="help-li-gap"><strong>Light Sensor Position:</strong> The light sensor should be positioned <strong>right between your eyebrows</strong>.</li>
                    <li className="help-li-gap"><strong>Electrode Position:</strong> The electrodes should be positioned <strong>2 inches above your eyebrows</strong> for optimal signal quality.</li>
                </ul>
                <p className="help-note help-note--green">
                    <strong>Tip:</strong> Proper positioning ensures accurate EEG readings. Take a moment to adjust the headset before starting calibration.
                </p>
            </>
        ),
    },
    {
        id: "charging",
        icon: faBatteryEmpty,
        title: "4. Removing the Amplifier for Charging",
        img: imgTakeOff,
        content: (
            <>
                <p>To charge the amplifier, you need to remove it from the clip:</p>
                <ol className="help-list-gap">
                    <li>Locate the clip that holds the amplifier to the headband.</li>
                    <li>Gently pull the amplifier <strong>out of the clip</strong>.</li>
                    <li>Connect the charging cable to the amplifier.</li>
                    <li>Charge until the indicator shows a full battery.</li>
                </ol>
                <p className="help-note help-note--yellow">
                    <strong>Note:</strong> The amplifier cannot be charged while attached to the headset clip.
                </p>
            </>
        ),
    },
    {
        id: "reinsert",
        icon: faPlug,
        title: "5. Inserting the Amplifier Back into the Clip",
        img: imgInsert,
        content: (
            <>
                <p>After charging, reattach the amplifier to the headset:</p>
                <ol className="help-list-gap">
                    <li>Hold the amplifier with the correct orientation.</li>
                    <li>Align the amplifier with the clip opening.</li>
                    <li>Gently push the amplifier into the clip until it <strong>clicks securely</strong>.</li>
                    <li>Ensure the amplifier is firmly attached before wearing the headset.</li>
                </ol>
                <p className="help-note help-note--green">
                    <strong>Important:</strong> Make sure the amplifier is properly seated to maintain good electrode contact.
                </p>
            </>
        ),
    },
];

const MANUAL_TOPICS = [
    {
        title: "Application Workflow",
        content: "The MindLink Analyzer guides you through a 7-step workflow: Region selection right arrow Login right arrow Live EEG verification right arrow Baseline calibration right arrow Task selection right arrow Task execution right arrow Results upload. Each step is shown in the page subtitle.",
    },
    {
        title: "Signal Quality Indicators",
        content: "The status bar shows real-time EEG signal quality. Green (Good) means the headset is properly placed and the signal is clean. Yellow (Noisy) means there may be movement or poor contact. Red / Not Worn means the electrode has no skin contact, reposition the headset.",
    },
    {
        title: "Baseline Calibration",
        content: "Two 30-second phases are recorded: Eyes Closed (EC) and Eyes Open (EO). Sit still and relax. The calibration establishes your personal baseline used to normalise all subsequent task recordings.",
    },
    {
        title: "Cognitive Tasks",
        content: "Each task runs for 45 to 114 seconds. Follow the on-screen instructions closely. Remain as still as possible to minimise movement artefacts. After all selected tasks are complete, proceed to the upload screen.",
    },
    {
        title: "Uploading Results",
        content: "On the Upload page, click Run Analysis to compute your EEG feature profile. You can then download the report as a text file or upload it directly to your Mindspeller account.",
    },
    {
        title: "Troubleshooting",
        content: "If the signal shows Not Worn: reposition the headset and press the forehead electrode firmly. If the signal stays Noisy: check Bluetooth connection and try moving away from other electronic devices. If the app cannot find the headset: ensure the device is paired via Windows Bluetooth settings first.",
    },
    {
        title: "Contact and Support",
        content: "For technical support, contact contact@mindspeller.com. Include your OS version, app version (shown in the footer), and a description of the issue.",
    },
];

const TIPS = [
    {
        title: "Slight noisy readings are normal",
        content: "EEG signals are very sensitive and can pick up minor movements or muscle activity. A few yellow (Noisy) readings during a session are normal. Focus on keeping the signal mostly green (Good) and avoid red (Not Worn) readings.",
    },
    {
        title: "Ensure good skin contact",
        content: "The forehead electrode needs firm contact with clean, dry skin. Remove any hair from the electrode area and press the headset gently but firmly against your forehead before starting.",
    },
    {
        title: "Charge before a session",
        content: "A low battery can cause signal dropouts mid-session. Always check that the amplifier is fully charged before you begin a recording session.",
    },
    {
        title: "Complete baseline calibration carefully",
        content: "The baseline is used to normalise all task results. Rushing or moving during the 30-second calibration phases will reduce the accuracy of your entire session.",
    },
    {
        title: "Re-run a task if something goes wrong",
        content: "If you were disturbed during a task (noise, movement, distraction), you can run it again from the task list. Only the latest recording is used in the analysis.",
    },
    {
        title: "Use a quiet, well-lit room",
        content: "For eyes-open tasks (e.g. Emotion Recognition, Creative Fluency), consistent ambient lighting reduces visual noise. A quiet environment helps with cognitive focus tasks.",
    },
];

const HelpPage = () => {
    const navigate = useNavigate();
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
                        <h1 className="help-page-title">Help &amp; User Manual</h1>
                        <p className="help-page-subtitle">Hardware setup instructions and application guidance</p>
                    </div>

                    <div className="help-tab-bar">
                        {[
                            { id: "started", icon: faRocket, label: "Getting Started" },
                            { id: "manual", icon: faBookOpen, label: "User Manual" },
                            { id: "tips", icon: faLightbulb, label: "Tips" },
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
                            {MANUAL_TOPICS.map((topic, idx) => (
                                <div key={idx} className="help-card">
                                    <button
                                        className="help-card-trigger"
                                        onClick={() => toggleManual(idx)}
                                    >
                                        <span className="help-num-badge">{idx + 1}</span>
                                        <span className="help-card-title">{topic.title}</span>
                                        <span className="help-toggle">
                                            {expandedManual === idx ? "\u2212" : "+"}
                                        </span>
                                    </button>

                                    {expandedManual === idx && (
                                        <div className="help-card-body--manual">
                                            {topic.content}
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    )}

                    {activeTab === "tips" && (
                        <div className="help-accordion">
                            {TIPS.map((tip, idx) => (
                                <div key={idx} className="help-card">
                                    <button
                                        className="help-card-trigger"
                                        onClick={() => toggleTip(idx)}
                                    >
                                        <span className="help-icon-badge help-icon-badge--tip">
                                            <FontAwesomeIcon icon={faLightbulb} />
                                        </span>
                                        <span className="help-card-title">{tip.title}</span>
                                        <span className="help-toggle">
                                            {expandedTip === idx ? "−" : "+"}
                                        </span>
                                    </button>
                                    {expandedTip === idx && (
                                        <div className="help-card-body--manual">
                                            {tip.content}
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    )}

                    <div className="help-back-row">
                        <button className="btn-back" onClick={() => navigate(-1)}>
                            <FontAwesomeIcon icon={faArrowLeft} /> Back
                        </button>
                    </div>
                </div>
            </main>
            <Footer />
        </div>
    );
};

export default HelpPage;
