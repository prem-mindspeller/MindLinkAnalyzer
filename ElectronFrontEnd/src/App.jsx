import React from 'react';
import { HashRouter, Routes, Route, Navigate } from 'react-router-dom';
import RegionPage from './pages/region';
import LoginPage from './pages/login';
import LiveEegReading from './pages/liveEegReding';
import BaselineCalibration1 from './pages/BaselineCalibration1';
import TaskSelection from './pages/TaskSelection';
import UploadPage from './pages/upload';
import HelpPage from './pages/help';
import './styles/main.css';
import HomePage from './pages/home';

function App() {
    return (
        <HashRouter>
            <Routes>
                <Route path="/" element={<Navigate to="/homePage" replace />} />
                <Route path="/homePage" element={<HomePage />} />
                <Route path="/region" element={<RegionPage />} />
                <Route path="/login" element={<LoginPage />} />
                <Route path="/liveReading" element={<LiveEegReading />} />
                <Route path="/baselineCalibration1" element={<BaselineCalibration1 />} />
                <Route path="/taskSelection" element={<TaskSelection />} />
                <Route path="/upload" element={<UploadPage />} />
                <Route path="/help" element={<HelpPage />} />
            </Routes>
        </HashRouter>
    );
}

export default App;
