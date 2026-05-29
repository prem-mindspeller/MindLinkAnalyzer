import React from 'react';
import { useTranslation } from 'react-i18next';

const { version } = require('../../package.json');

const Footer = () => {
    const { t } = useTranslation();
    return (
        <footer className="app-footer">
            <p>{t('footer.text', { version, year: new Date().getFullYear() })}</p>
        </footer>
    );
}

export default Footer;