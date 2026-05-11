import React, { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

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
    const { i18n } = useTranslation();
    const [open, setOpen] = useState(false);
    const rootRef = useRef(null);
    const activeLanguage = LANGUAGES.find(lang => lang.code === i18n.language) || LANGUAGES[0];

    useEffect(() => {
        const handleClickOutside = (event) => {
            if (rootRef.current && !rootRef.current.contains(event.target)) {
                setOpen(false);
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    const selectLanguage = (code) => {
        i18n.changeLanguage(code);
        sessionStorage.setItem('language', code);
        setOpen(false);
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
