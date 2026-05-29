import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';

const { ipcRenderer } = window.require('electron');
const { version } = require('../../package.json');

const Footer = () => {
    const { t } = useTranslation();
    const [updateStatus, setUpdateStatus] = useState(null); // null | 'checking' | 'downloading' | 'up-to-date' | 'error'

    useEffect(() => {
        const handler = (_event, status) => setUpdateStatus(status);
        ipcRenderer.on('update-status', handler);
        return () => ipcRenderer.removeListener('update-status', handler);
    }, []);

    const handleCheckUpdates = async () => {
        setUpdateStatus('checking');
        await ipcRenderer.invoke('check-for-updates');
        // Status will be updated via 'update-status' IPC event from main
        // Fall back to 'up-to-date' after 10s if no event received
        setTimeout(() => setUpdateStatus(s => s === 'checking' ? 'up-to-date' : s), 10000);
    };

    const statusLabel = {
        checking: 'Checking...',
        downloading: 'Downloading update...',
        'up-to-date': 'Up to date',
        error: 'Update check failed',
    }[updateStatus];

    return (
        <footer className="app-footer">
            <p>{t('footer.text', { version, year: new Date().getFullYear() })}</p>
            <button
                onClick={handleCheckUpdates}
                disabled={updateStatus === 'checking' || updateStatus === 'downloading'}
                style={{
                    marginTop: '4px',
                    fontSize: '0.75rem',
                    padding: '2px 10px',
                    cursor: 'pointer',
                    opacity: (updateStatus === 'checking' || updateStatus === 'downloading') ? 0.6 : 1
                }}
            >
                {statusLabel || 'Check for updates'}
            </button>
        </footer>
    );
}

export default Footer;