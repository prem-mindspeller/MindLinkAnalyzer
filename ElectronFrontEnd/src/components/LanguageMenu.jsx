import React, { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { hasPendingInTaskAudioTranslation } from './inTaskAudioAvailability.mjs';

const LANGUAGES = [
    { code: 'en', label: 'English' },
    { code: 'nl', label: 'Nederlands' },
    { code: 'de', label: 'Deutsch' },
    { code: 'fr', label: 'Français' },
    { code: 'es', label: 'Español' },
    { code: 'it', label: 'Italiano' },
    { code: 'pt', label: 'Português' },
    { code: 'hi', label: 'हिन्दी' },
    { code: 'ar', label: 'العربية' },
    { code: 'ja', label: '日本語' },
];

const LanguageMenu = () => {
    const { i18n, t } = useTranslation();
    const [open, setOpen] = useState(false);
    const rootRef = useRef(null);
    const activeLanguageCode = (i18n.resolvedLanguage || i18n.language || 'en').split('-')[0];
    const activeLanguage = LANGUAGES.find(lang => lang.code === activeLanguageCode) || LANGUAGES[0];

    useEffect(() => {
        const handleClickOutside = (event) => {
            if (rootRef.current && !rootRef.current.contains(event.target)) {
                setOpen(false);
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    const selectLanguage = async (code) => {
        const changed = code !== activeLanguageCode;
        await i18n.changeLanguage(code);
        sessionStorage.setItem('language', code);
        setOpen(false);
        if (changed && hasPendingInTaskAudioTranslation(code)) {
            window.alert(t('optimizedBattery.audioTranslationPending', {
                defaultValue: 'Some in-task audio is currently English. We are working on translations for your selected language.',
            }));
        }
    };

    return (
        <div className={`badge language-badge${open ? ' open' : ''}`} ref={rootRef}>
            <button
                type="button"
                className="language-trigger"
                aria-haspopup="listbox"
                aria-expanded={open}
                onClick={() => setOpen(value => !value)}
            >
                <span className="language-current">{activeLanguage.label}</span>
                <span className="language-chevron">▾</span>
            </button>
            {open && (
                <div className="language-menu" role="listbox" aria-label="Language">
                    {LANGUAGES.map(lang => (
                        <button
                            key={lang.code}
                            type="button"
                            role="option"
                            aria-selected={lang.code === activeLanguage.code}
                            className={`language-option${lang.code === activeLanguage.code ? ' active' : ''}`}
                            onClick={() => selectLanguage(lang.code)}
                        >
                            {lang.label}
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
};

export default LanguageMenu;
