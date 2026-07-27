import i18n from '../i18n';
import { resolveBookingAccess } from './bookingAccess.mjs';

const API_ENDPOINTS = {
    en: 'https://en.mindspeller.com',
    nl: 'https://nl.mindspeller.com',
};

const loginUser = async (email, password, region = 'en') => {
    const baseUrl = API_ENDPOINTS[region]
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

        sessionStorage.setItem('jwtToken', token);
        sessionStorage.setItem('loggedInUser', email);
        sessionStorage.setItem('region', region);
        if (data['x-jwt-refresh-token']) {
            sessionStorage.setItem('jwtRefreshToken', data['x-jwt-refresh-token']);
        }
        _startRefreshInterval();

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


const getToken = () => {
    return sessionStorage.getItem('jwtToken');
};


const getUser = () => {
    return sessionStorage.getItem('loggedInUser');
};


const getRegion = () => {
    return sessionStorage.getItem('region') || 'en';
};

const logout = () => {
    _stopRefreshInterval();
    sessionStorage.removeItem('jwtToken');
    sessionStorage.removeItem('jwtRefreshToken');
    sessionStorage.removeItem('loggedInUser');
    sessionStorage.removeItem('region');
    window.dispatchEvent(new Event('app:logout'));
};

let _refreshTimer = null;

const _refreshToken = async () => {
    const refreshToken = sessionStorage.getItem('jwtRefreshToken');
    const region = getRegion();
    const baseUrl = API_ENDPOINTS[region];
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
            logout();
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
    const baseUrl = API_ENDPOINTS[region];

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
    getToken,
    getUser,
    getRegion,
    logout,
    isAuthenticated,
    checkPartnerBookings,
    refreshToken: _refreshToken,
};

export default loginService;
