import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import Footer from '../components/footer';
import Header from '../components/header';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faArrowRight } from '@fortawesome/free-solid-svg-icons';
import '../styles/regionpage.css';
import RegionSelectionCard from '../components/region/regionselectionCard';
import StepsComponent from '../components/region/stepsComponent';

const RegionPage = () => {
    const navigate = useNavigate();
    const { t } = useTranslation();

    const handleNext = () => {
        navigate('/login');
    };

    return (
        <>
            <div className="app-container region-app-container">
                <Header />
                <main className="app-main">
                    <div className="region-page">
                        <h1 className="rp-title">
                            {t('region.welcome')} <span className="rp-title-accent">{t('region.appName')}</span>
                        </h1>
                        <p className="rp-subtitle">
                            {t('region.description')}
                        </p>
                        <div className='content'>
                            <RegionSelectionCard />
                        </div>

                        <div className="navigation-buttons">
                            <button className="btn-next" onClick={handleNext}>
                                {t('region.getStarted')} <FontAwesomeIcon icon={faArrowRight} style={{ marginLeft: 6 }} />
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