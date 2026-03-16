import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Footer from '../components/footer';
import Header from '../components/header';
import '../styles/regionpage.css';
import RegionSelectionCard from '../components/region/regionselectionCard';

const RegionPage = () => {
    const navigate = useNavigate();

    const handleNext = () => {
        navigate('/login');
    };

    const handleBack = () => {
        navigate(-1);
    };

    return (
        <>
            <div className="app-container">
                <Header />
                <main className="app-main">
                    <div className="region-page">
                        <RegionSelectionCard />


                        <div className="navigation-buttons">
                            <button className="btn-back" onClick={handleBack}>
                                ← Back
                            </button>
                            <button className="btn-next" onClick={handleNext}>
                                Next →
                            </button>
                        </div>
                    </div>
                </main>
                <Footer />
            </div>
        </>

    );
}

export default RegionPage;