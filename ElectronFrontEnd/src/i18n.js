import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import en from './locales/en.json';
import nl from './locales/nl.json';
import de from './locales/de.json';
import fr from './locales/fr.json';
import es from './locales/es.json';
import it from './locales/it.json';
import pt from './locales/pt.json';
import hi from './locales/hi.json';
import ar from './locales/ar.json';
import ja from './locales/ja.json';

i18n
    .use(initReactI18next)
    .init({
        resources: {
            en: { translation: en },
            nl: { translation: nl },
            de: { translation: de },
            fr: { translation: fr },
            es: { translation: es },
            it: { translation: it },
            pt: { translation: pt },
            hi: { translation: hi },
            ar: { translation: ar },
            ja: { translation: ja },
        },
        lng: sessionStorage.getItem('language') || 'en',
        fallbackLng: 'en',
        interpolation: { escapeValue: false },
    });

const applyDocumentLanguage = (lng) => {
    if (typeof document === 'undefined') return;
    const language = (lng || 'en').split('-')[0];
    document.documentElement.lang = language;
    document.documentElement.dir = language === 'ar' ? 'rtl' : 'ltr';
};

applyDocumentLanguage(i18n.language);
i18n.on('languageChanged', applyDocumentLanguage);

export default i18n;
