function updateToken() {
  if (isRefreshing && refreshPromise) {
    return refreshPromise;
  }
  isRefreshing = true;
  refreshPromise = _doUpdateToken().finally(() => {
    isRefreshing = false;
    refreshPromise = null;
  });
  return refreshPromise;
}

function _doUpdateToken() {
  const isAnonymous = getStorageItem(STORAGE_KEYS.IS_ANONYMOUS);
  const jwtToken = getStorageItem(STORAGE_KEYS.JWT_TOKEN);
  const refreshToken = getStorageItem(STORAGE_KEYS.JWT_REFRESH_TOKEN);

  // PRIORITY FIX: Protection against transitions to anonymous state during username changes
  // If we have valid tokens but somehow the anonymous flag is true, this is a critical error
  if (jwtToken && refreshToken && isAnonymous === 'true') {
    // Fix the inconsistent state by setting anonymous to false
    setStorageItem(STORAGE_KEYS.IS_ANONYMOUS, 'false');

    // Check if this error occurred on My Account page during/after username change
    // Proceed with normal user token refresh, using the refresh token we already have
    return refreshUserToken(refreshToken);
  }

  // Case 1: User is on the network page without tokens
  if (isNetworkPage() && !jwtToken) {
    clearAuthData();
    return refreshNetworkToken();
  }

  // Case 2: User has a refresh token and is not anonymous and not on network page
  else if (refreshToken && isAnonymous !== 'true' && !isNetworkPage()) {
    return refreshUserToken(refreshToken);
  }

  // Case 3: User is on network page and is anonymous
  else if (isAnonymous === 'true' && isNetworkPage()) {
    // Already anonymous and on network page, no need to refresh
    return Promise.resolve();
  }

  // Case 4: User is anonymous (network user) but not on network page
  else if (isAnonymous === 'true' && !window.location.hash.includes('/respondent_signup') && !window.location.hash.includes('/login')) {
    // Special protection: If user is on a protected page (like my_account) but isAnonymous='true',
    // this might be a session error after username change. Check if we have tokens first.
    if (jwtToken && refreshToken) {
      // Fix the state by setting anonymous to false and refreshing the user token
      setStorageItem(STORAGE_KEYS.IS_ANONYMOUS, 'false');
      return refreshUserToken(refreshToken).then(response => {
        // Force page reload to apply fixed session state if this was on My Account page
        if (window.location.hash.includes('/my_account')) {
          window.location.reload();
        }
        return response;
      });
    }

    // Don't clear auth if we have tokens - the user might be transitioning from logged in to anonymous
    if (!jwtToken && !refreshToken) {
      clearAuthData();
    }
    // If we're not already navigating to login/signup, get a network token
    return refreshNetworkToken();
  }

  // Case 5: No valid tokens - passive handling, no error
  else {
    return Promise.resolve();
  }
}

function refreshNetworkToken() {
  return axios.post('/api/cas/token/refresh_for_network', {})
    .then(response => {
      if (response.data && response.data['x-jwt-access-token']) {
        // Use login helper to store tokens consistently
        login(response.data['x-jwt-access-token'], response.data['x-jwt-refresh-token']);
        setStorageItem(STORAGE_KEYS.IS_ANONYMOUS, 'true');
        return response;
      }
      throw new Error('Invalid network token response');
    })
    .catch(error => {
      // Report token refresh errors with context
      errorReporter.handleAxiosError(error, {
        component: 'AxiosHelper',
        action: 'refreshNetworkToken'
      });
      return Promise.reject(error);
    });
}

function refreshUserToken(refreshToken) {
  const config = {
    headers: {
      'Authorization': `Bearer ${refreshToken}`,
      'X-Authorization': `Bearer ${refreshToken}`
    },
    mdsp_retry: true,
    skipTokenInjection: true // Prevent interceptor from injecting expired token
  };

  return axios.post('/api/cas/token/refresh', {}, config)
    .then(response => {
      if (response.data && response.data['x-jwt-access-token']) {
        // Use login helper to store tokens consistently and extract userID data
        login(response.data['x-jwt-access-token'], response.data['x-jwt-refresh-token']);

        // Update axios defaults
        axios.defaults.headers.common['X-Authorization'] = `Bearer ${response.data['x-jwt-access-token']}`;
        axios.defaults.headers.common['Authorization'] = `Bearer ${response.data['x-jwt-access-token']}`;

        // Parse authentication response metadata
        const metadata = response.data.metadata || {};
        const hasIdBasedAuth = response.headers['x-id-based-authentication'] === 'true' ||
          metadata.id_based_authentication === true;

        // Broadcast token refresh event with userID data
        try {
          import('@/eventBus').then(({ EventBus }) => {
            EventBus.emit('tokens:refreshed', {
              accessToken: response.data['x-jwt-access-token'],
              refreshToken: response.data['x-jwt-refresh-token'],
              metadata: metadata,
              hasIdBasedAuth: hasIdBasedAuth
            });
          }).catch(() => {});
        } catch (e) {}

        return response;
      }
      throw new Error('Invalid user token response');
    })
    .catch(error => {
      if (error.response && error.response.status === 401) {
        clearAuthData();
        // Only redirect to signup if NOT on a landing page - let users browse landing pages without forced redirect
        if (!isNetworkPage()) {
          window.location.replace('/#/respondent_signup');
        }
      } else {
        // Report token refresh errors with context
        errorReporter.handleAxiosError(error, {
          component: 'AxiosHelper',
          action: 'refreshUserToken'
        });
      }
      return Promise.reject(error);
    });
}
// Refresh token periodically (but skip on landing pages to avoid unwanted redirects)
setInterval(function () {
  if (!isNetworkPage()) {
    updateToken();
  }
}, 14 * 60 * 1000);
