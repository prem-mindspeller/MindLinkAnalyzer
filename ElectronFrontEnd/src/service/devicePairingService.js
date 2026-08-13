import i18n from '../i18n';
import loginService from './loginService';


const POLL_STATUS = {
    PENDING: 'pending',
    APPROVED: 'approved',
    EXPIRED: 'expired',
    NOT_FOUND: 'not_found',
    INVALID: 'invalid',
    ERROR: 'error',
};

const buildVerificationUrl = (code, region = 'en') => {
    const webBase = loginService.getWebBase(region);
    return `${webBase}/#/device-link?code=${encodeURIComponent(code)}`;
};


const startPairing = async (region = 'en') => {
    const baseUrl = loginService.getApiBase(region);

    const deviceLabel = `MindLink desktop (${navigator.platform || 'unknown'})`;

    const response = await fetch(`${baseUrl}/api/cas/device/pair/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device_label: deviceLabel, region }),
    });

    if (!response.ok) {
        throw new Error(i18n.t('errors.qrStartFailedStatus', { status: response.status }));
    }

    const data = await response.json();
    if (!data || !data.success || !data.code) {
        throw new Error(i18n.t('errors.qrStartFailed'));
    }

    return {
        code: data.code,
        deviceSecret: data.device_secret,
        expiresIn: data.expires_in || 180,
        // Never poll faster than the backend asked for.
        interval: Math.max(data.interval || 3, 2),
        verificationUrl: buildVerificationUrl(data.code, region),
    };
};


const pollPairing = async (code, deviceSecret, region = 'en') => {
    const baseUrl = loginService.getApiBase(region);

    let response;
    try {
        response = await fetch(`${baseUrl}/api/cas/device/pair/poll`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code, device_secret: deviceSecret }),
        });
    } catch (err) {

        return { status: POLL_STATUS.ERROR, transient: true };
    }

    let data = null;
    try {
        data = await response.json();
    } catch (err) {
        return { status: POLL_STATUS.ERROR, transient: true };
    }

    const status = (data && data.status) || POLL_STATUS.ERROR;

    if (status === POLL_STATUS.APPROVED && data['x-jwt-access-token']) {
        loginService.applySession(data, data.email, region);
        return { status: POLL_STATUS.APPROVED, email: data.email };
    }

    return { status, transient: false };
};

const devicePairingService = {
    startPairing,
    pollPairing,
    buildVerificationUrl,
    POLL_STATUS,
};

export default devicePairingService;
