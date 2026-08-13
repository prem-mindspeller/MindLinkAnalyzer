import i18n from '../i18n';
import { resolveBookingAccess } from './bookingAccess.mjs';
import { clearBatteryRunData } from './batteryRunCleanup.mjs';

const API_ENDPOINTS = {
    // en:'http://127.0.0.1:5000',
    en: 'https://en.mindspeller.com',
    nl: 'https://nl.mindspeller.com',
};

// The web app lives on a different host from the API above. Used to build the
// link the phone opens during QR device pairing.
const WEB_ENDPOINTS = {
    // en:'http://localhost:8080',
    en: 'https://mindspeller.com',
    nl: 'https://cas-nl.mindspeller.com',
};

// Local-development escape hatch. Unset in any normal run, so these resolve to
// the production hosts above and behaviour is unchanged. To point a dev build
// at a local stack, run this once in the DevTools console:
//
//   localStorage.setItem('mdsp_dev_api_base', 'http://localhost:5000')
//   localStorage.setItem('mdsp_dev_web_base', 'http://localhost:8080')
//
// and localStorage.removeItem(...) to go back to production.
const devOverride = (key) => {
    try {
        const value = localStorage.getItem(key);
        return value && value.trim() ? value.trim().replace(/\/+$/, '') : null;
    } catch (err) {
        return null;
    }
};

const getApiBase = (region = 'en') =>
    devOverride('mdsp_dev_api_base') || API_ENDPOINTS[region] || API_ENDPOINTS.en;
const getWebBase = (region = 'en') =>
    devOverride('mdsp_dev_web_base') || WEB_ENDPOINTS[region] || WEB_ENDPOINTS.en;

const loginUser = async (email, password, region = 'en') => {
    const baseUrl = getApiBase(region)
    const loginUrl = `${baseUrl}/api/cas/token/login`;

    const loginPayload = {
        username: email,
        password: password
    };

    try {
        const response = await fetch(loginUrl, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify(loginPayload),
        });

        if (!response.ok) {
            const status = response.status;
            let message;
            if (status === 401 || status === 403) {
                message = i18n.t('errors.incorrectCredentials');
            } else if (status === 503 || status === 502) {
                message = i18n.t('errors.serverUnavailable');
            } else if (status >= 500) {
                message = i18n.t('errors.serverError', { status });
            } else if (status === 404) {
                message = i18n.t('errors.loginServiceNotFound');
            } else {
                message = i18n.t('errors.loginFailedStatus', { status });
            }
            throw new Error(message);
        }

        const data = await response.json();
        const token = data["x-jwt-access-token"];

        if (!token) {
            throw new Error(i18n.t('errors.noAuthToken'));
        }

        applySession(data, email, region);

        return {
            success: true,
            token: token,
            user: email,
            data: data
        };
    } catch (error) {
        return {
            success: false,
            error: error.message
        };
    }
};


const applySession = (data, email, region = 'en') => {
    sessionStorage.setItem('jwtToken', data['x-jwt-access-token']);
    sessionStorage.setItem('loggedInUser', email);
    sessionStorage.setItem('region', region);
    if (data['x-jwt-refresh-token']) {
        sessionStorage.setItem('jwtRefreshToken', data['x-jwt-refresh-token']);
    }
    _startRefreshInterval();
};


const getToken = () => {
    return sessionStorage.getItem('jwtToken');
};


const getUser = () => {
    return sessionStorage.getItem('loggedInUser');
};


const getRegion = () => {
    return sessionStorage.getItem('region') || 'en';
};

const logout = async () => {
    _stopRefreshInterval();
    let cleanupError = null;
    try {
        await clearBatteryRunData(sessionStorage);
    } catch (error) {
        cleanupError = error;
    } finally {
        // Authentication teardown remains unconditional even if the local
        // recording database reports a cleanup error.
        sessionStorage.removeItem('jwtToken');
        sessionStorage.removeItem('jwtRefreshToken');
        sessionStorage.removeItem('loggedInUser');
        sessionStorage.removeItem('region');
        window.dispatchEvent(new Event('app:logout'));
    }
    if (cleanupError) throw cleanupError;
};

let _refreshTimer = null;

const _refreshToken = async () => {
    const refreshToken = sessionStorage.getItem('jwtRefreshToken');
    const region = getRegion();
    const baseUrl = getApiBase(region);
    if (!refreshToken) return;

    try {
        const response = await fetch(`${baseUrl}/api/cas/token/refresh`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${refreshToken}`,
                'X-Authorization': `Bearer ${refreshToken}`,
            },
        });

        if (response.status === 401) {
            await logout();
            return;
        }

        if (!response.ok) {
            return;
        }

        const data = await response.json();
        if (data['x-jwt-access-token']) {
            sessionStorage.setItem('jwtToken', data['x-jwt-access-token']);
        }
        if (data['x-jwt-refresh-token']) {
            sessionStorage.setItem('jwtRefreshToken', data['x-jwt-refresh-token']);
        }
    } catch (err) {}
};

const _startRefreshInterval = () => {
    _stopRefreshInterval();
    _refreshTimer = setInterval(_refreshToken, 10 * 60 * 1000);
};

const _stopRefreshInterval = () => {
    if (_refreshTimer) {
        clearInterval(_refreshTimer);
        _refreshTimer = null;
    }
};

const checkPartnerBookings = async (partnerId) => {
    const token = getToken();
    const region = getRegion();
    const baseUrl = getApiBase(region);

    try {
        const response = await fetch(
            `${baseUrl}/api/cas/partners/bookings?partner_id=${encodeURIComponent(partnerId)}`,
            {
                method: 'GET',
                headers: {
                    'X-Authorization': `Bearer ${token}`
                }
            }
        );

        if (response.status === 404) {
            return { success: false, notFound: true, hasSessionOne: false, hasAdvancedBooking: false, hasSessionThree: false };
        }

        if (!response.ok) {
            throw new Error(i18n.t('errors.unexpectedError', { status: response.status }));
        }

        const data = await response.json();
        const access = resolveBookingAccess(data);

        return {
            success: true,
            notFound: false,
            ...access,
        };
    } catch (error) {
        return {
            success: false,
            notFound: false,
            hasSessionOne: false,
            hasAdvancedBooking: false,
            hasSessionThree: false,
            error: error.message,
        };
    }
};


const isAuthenticated = () => {
    return !!getToken();
};

const loginService = {
    loginUser,
    applySession,
    getApiBase,
    getWebBase,
    getToken,
    getUser,
    getRegion,
    logout,
    isAuthenticated,
    checkPartnerBookings,
    refreshToken: _refreshToken,
};

export default loginService;
