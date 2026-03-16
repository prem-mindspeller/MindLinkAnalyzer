const API_ENDPOINTS = {
    en: "https://stg-en.mindspell.be",
    nl: "https://stg-nl.mindspell.be",
    local: "http://127.0.0.1:5000"
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
            const errorText = await response.text();
            throw new Error(`Login failed: ${response.status} - ${errorText}`);
        }

        const data = await response.json();
        const token = data["x-jwt-access-token"];

        if (!token) {
            throw new Error("No authentication token received");
        }

        sessionStorage.setItem('jwtToken', token);
        sessionStorage.setItem('loggedInUser', email);
        sessionStorage.setItem('region', region);

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
    sessionStorage.removeItem('jwtToken');
    sessionStorage.removeItem('loggedInUser');
    sessionStorage.removeItem('region');

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
            return { success: false, notFound: true, hasAdvancedBooking: false };
        }

        if (!response.ok) {
            throw new Error(`Unexpected error: ${response.status}`);
        }

        const data = await response.json();

        let hasAdvancedBooking = false;
        if (typeof data.has_booking !== 'undefined') {
            hasAdvancedBooking = Boolean(data.has_booking);
        } else if (Array.isArray(data.bookings)) {
            hasAdvancedBooking = data.bookings.length > 0;
        } else if (data.data && typeof data.data.has_booking !== 'undefined') {
            hasAdvancedBooking = Boolean(data.data.has_booking);
        }

        return { success: true, notFound: false, hasAdvancedBooking };
    } catch (error) {
        console.error('Error checking partner:', error);
        return { success: false, notFound: false, hasAdvancedBooking: false, error: error.message };
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
    checkPartnerBookings
};

export default loginService;