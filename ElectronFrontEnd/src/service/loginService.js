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
                message = 'Incorrect email or password. Please try again.';
            } else if (status === 503 || status === 502) {
                message = 'The server is temporarily unavailable. Please try again in a few minutes.';
            } else if (status >= 500) {
                message = `Server error (${status}). Please try again later.`;
            } else if (status === 404) {
                message = 'Login service not found. Please check your region selection.';
            } else {
                message = `Login failed (${status}). Please try again.`;
            }
            throw new Error(message);
        }

        const data = await response.json();
        const token = data["x-jwt-access-token"];

        if (!token) {
            throw new Error("No authentication token received");
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
        console.error('Login error:', error);
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
            console.warn('[tokenRefresh] Refresh token expired, logging out.');
            logout();
            return;
        }

        if (!response.ok) {
            console.error('[tokenRefresh] Refresh failed:', response.status);
            return;
        }

        const data = await response.json();
        if (data['x-jwt-access-token']) {
            sessionStorage.setItem('jwtToken', data['x-jwt-access-token']);
        }
        if (data['x-jwt-refresh-token']) {
            sessionStorage.setItem('jwtRefreshToken', data['x-jwt-refresh-token']);
        }
        console.log('[tokenRefresh] Token refreshed successfully.');
    } catch (err) {
        console.error('[tokenRefresh] Error during refresh:', err);
    }
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
            return { success: false, notFound: true, hasAdvancedBooking: false, hasTwoBookings: false };
        }

        if (!response.ok) {
            throw new Error(`Unexpected error: ${response.status}`);
        }

        const data = await response.json();

        let hasAdvancedBooking = false;
        let hasTwoBookings = false;

        // Helper: count from any bookings array in the response
        const _countBookings = (obj) => {
            if (Array.isArray(obj.partner_bookings)) return obj.partner_bookings.length;
            if (Array.isArray(obj.bookings))         return obj.bookings.length;
            if (typeof obj.booking_count === 'number') return obj.booking_count;
            return 0;
        };

        if (typeof data.has_booking !== 'undefined') {
            hasAdvancedBooking = Boolean(data.has_booking);
            const count = _countBookings(data);
            hasTwoBookings = count >= 2;
        } else if (Array.isArray(data.partner_bookings)) {
            hasAdvancedBooking = data.partner_bookings.length > 0;
            hasTwoBookings     = data.partner_bookings.length >= 2;
        } else if (Array.isArray(data.bookings)) {
            hasAdvancedBooking = data.bookings.length > 0;
            hasTwoBookings     = data.bookings.length >= 2;
        } else if (data.data && typeof data.data.has_booking !== 'undefined') {
            hasAdvancedBooking = Boolean(data.data.has_booking);
            const count = _countBookings(data.data);
            hasTwoBookings = count >= 2;
        }

        return { success: true, notFound: false, hasAdvancedBooking, hasTwoBookings };
    } catch (error) {
        console.error('Error checking partner:', error);
        return { success: false, notFound: false, hasAdvancedBooking: false, hasTwoBookings: false, error: error.message };
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