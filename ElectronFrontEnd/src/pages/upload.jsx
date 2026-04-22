import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import LoggedInHeader from '../components/LoggedInHeader';
import Footer from '../components/footer';
import AnalysisResultsPanel from '../components/AnalysisResultsPanel';
import { runAnalysis, seedReport, buildReportText } from '../service/analysisService';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import {
    faPlay, faSpinner, faDownload, faCloud,
    faArrowLeft, faCheck,
} from '@fortawesome/free-solid-svg-icons';
import '../styles/liveEegReading.css';
import '../styles/upload.css';
import loginService from '../service/loginService';
import wsEegService from '../service/wsEegService';

const STATUS = {
    IDLE: 'idle',
    RUNNING: 'running',
    DONE: 'done',
    ERROR: 'error',
};

const UploadPage = () => {
    const navigate = useNavigate();

    const [status, setStatus] = useState(STATUS.IDLE);
    const [results, setResults] = useState(null);
    const [errorMsg, setErrorMsg] = useState('');
    const [seedStatus, setSeedStatus] = useState(null); // null | 'seeding' | 'success' | 'error'
    const [seedMsg, setSeedMsg] = useState('');
    const [notUploadedProfile, setNotUploadedProfile] = useState(true);
    const [showDownloadProfileButton, setShowDownloadProfileButton] = useState(false);


    const hasCompletedInitial = Boolean(
        JSON.parse(sessionStorage.getItem('userData') || '{}').initial_protocol
    );

    const handleAnalyse = async () => {
        setStatus(STATUS.RUNNING);
        setErrorMsg('');
        setResults(null);
        try {
            const data = await runAnalysis();
            setResults(data);
            setStatus(STATUS.DONE);
        } catch (err) {
            setErrorMsg(err.message);
            setStatus(STATUS.ERROR);
        }
    };

    const handleDownload = () => {
        if (!results) return;
        const text = buildReportText(results);
        const blob = new Blob([text], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `Mindlink_report_${Date.now()}.txt`;
        a.click();
        URL.revokeObjectURL(url);
    };


    const handleSeed = async () => {
        if (seedStatus === 'seeding' || seedStatus === 'success') return;
        const email = loginService.getUser() || '';
        const protocolType = hasCompletedInitial ? 'advanced' : 'initial';
        setSeedStatus('seeding');
        try {
            await seedReport(email, protocolType, results);
            setSeedStatus('success');
            setSeedMsg('Report successfully seeded to Mindspeller database.');
            setNotUploadedProfile(false);
        } catch (err) {
            setSeedStatus('error');
            setSeedMsg(`Seeding failed: ${err.message}`);
            setShowDownloadProfileButton(true);
        }
    };

    const handleFinish = async () => {
        const completedIds = JSON.parse(sessionStorage.getItem('completedTasks') || '[]');
        for (const id of completedIds) {
            sessionStorage.removeItem(`taskData_${id}`);
        }
        sessionStorage.removeItem('completedTasks');
        await wsEegService.disconnect();
        loginService.logout();
        const { shell } = window.require('electron');
        shell.openExternal('https://www.mindspeller.com');
        navigate('/');
    };

    return (
        <div className="app-container">
            <LoggedInHeader />
            <main className="app-main">
                <div className="upload-page">


                    <div className="page-header-eeg">
                        <h1 className="page-title-eeg">Task Analysis</h1>
                        <p className="page-subtitle-eeg">Step 7 of 7: Analyse EEG data and send report</p>
                    </div>

                    <div className="upload-card">
                        <p className="upload-desc">
                            Click Analyze All Tasks to see how your brain responded to each challenge. This just takes a few seconds! Once your results appear, click Save Profile to securely upload your data and complete your assessment.
                        </p>

                        <div className="upload-actions">
                            <button
                                className={`upload-btn-primary${status === STATUS.DONE ? ' upload-btn-primary--done' : ''}`}
                                onClick={handleAnalyse}
                                disabled={status === STATUS.RUNNING || status === STATUS.DONE || seedStatus === 'success'}
                            >
                                {status === STATUS.RUNNING
                                    ? <><FontAwesomeIcon icon={faSpinner} spin style={{ marginRight: 8 }} />Analysing…</>
                                    : status === STATUS.DONE
                                        ? <><FontAwesomeIcon icon={faCheck} style={{ marginRight: 8 }} />Analysis Complete</>
                                        : <><FontAwesomeIcon icon={faPlay} style={{ marginRight: 8 }} />Analyse All Tasks</>}
                            </button>

                            {status === STATUS.DONE && (
                                <>
                                    {showDownloadProfileButton && (
                                        <button className="upload-btn-secondary" onClick={handleDownload}>
                                            <FontAwesomeIcon icon={faDownload} style={{ marginRight: 8 }} />Download Report
                                        </button>
                                    )}
                                    <button
                                        className="upload-btn-seed"
                                        onClick={handleSeed}
                                        disabled={seedStatus === 'seeding' || seedStatus === 'success'}
                                    >
                                        {seedStatus === 'seeding'
                                            ? <><FontAwesomeIcon icon={faSpinner} spin style={{ marginRight: 8 }} />uploading</>
                                            : seedStatus === 'success'
                                                ? <><FontAwesomeIcon icon={faCheck} style={{ marginRight: 8 }} />Uploaded</>
                                                : <><FontAwesomeIcon icon={faCloud} style={{ marginRight: 8 }} />Upload to Mindspeller</>}
                                    </button>
                                </>
                            )}
                        </div>

                        {status === STATUS.ERROR && (
                            <div className="upload-error">
                                <strong>Analysis failed:</strong> {errorMsg}
                            </div>
                        )}


                        {seedStatus === 'success' && (
                            <div className="upload-success">{seedMsg}</div>
                        )}
                        {seedStatus === 'error' && (
                            <div className="upload-error">{seedMsg}</div>
                        )}
                    </div>

                    {/* {results && <AnalysisResultsPanel results={results} />} */}

                    <div className="navigation-buttons-eeg">
                        <button className="btn-back-eeg" onClick={() => navigate('/taskSelection')}>
                            <FontAwesomeIcon icon={faArrowLeft} style={{ marginRight: 6 }} />Back
                        </button>
                        <button
                            className="btn-next-eeg"
                            disabled={notUploadedProfile}
                            onClick={handleFinish}
                        >
                            Finish <FontAwesomeIcon icon={faCheck} style={{ marginLeft: 6 }} />
                        </button>
                    </div>
                </div>
            </main>
            <Footer />



        </div>
    );
};

export default UploadPage;
