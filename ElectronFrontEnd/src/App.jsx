import React from 'react';
import { HashRouter, Routes, Route, Navigate } from 'react-router-dom';
import RegionPage from './pages/region';
import LoginPage from './pages/login';
import LiveEegReading from './pages/liveEegReding';
import PathwayPage from './pages/pathway';
import './styles/main.css';

function App() {
    return (
        <HashRouter>
            <Routes>
                <Route path="/" element={<Navigate to="/region" replace />} />
                <Route path="/region" element={<RegionPage />} />
                <Route path="/login" element={<LoginPage />} />
                <Route path="/liveReading" element={<LiveEegReading />} />
                <Route path="/pathway" element={<PathwayPage />} />
            </Routes>
        </HashRouter>
    );
}

export default App;
