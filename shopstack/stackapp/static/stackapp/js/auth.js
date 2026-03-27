/**
 * auth.js — shared authentication utilities for ShopStack UI.
 *
 * Exposes globals: getAccessToken, setTokens, clearTokens, getCsrfToken,
 * authFetch, requireAuth, logout.
 *
 * Design notes:
 * - All tokens are stored in localStorage under fixed keys.
 * - authFetch auto-refreshes on 401 using a single in-flight promise
 *   (refresh lock) to prevent concurrent refresh storms.
 * - Cross-tab logout via storage event.
 * - CSRF token sent on every non-GET request as defence-in-depth.
 */

'use strict';

const ACCESS_KEY = 'shopstack_access';
const REFRESH_KEY = 'shopstack_refresh';

// ---------------------------------------------------------------------------
// Token storage helpers
// ---------------------------------------------------------------------------

function getAccessToken() {
    return localStorage.getItem(ACCESS_KEY);
}

function getRefreshToken() {
    return localStorage.getItem(REFRESH_KEY);
}

function setTokens(access, refresh) {
    localStorage.setItem(ACCESS_KEY, access);
    localStorage.setItem(REFRESH_KEY, refresh);
}

function clearTokens() {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
}

// ---------------------------------------------------------------------------
// CSRF cookie reader
// ---------------------------------------------------------------------------

function getCsrfToken() {
    const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? match[1] : '';
}

// ---------------------------------------------------------------------------
// Token refresh — with race-condition lock
// ---------------------------------------------------------------------------

let _refreshPromise = null;

async function _doRefresh() {
    const refresh = getRefreshToken();
    if (!refresh) {
        throw new Error('No refresh token');
    }
    const resp = await fetch('/api/auth/token/refresh/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh }),
    });
    if (!resp.ok) {
        throw new Error('Refresh failed');
    }
    const data = await resp.json();
    // simplejwt rotates refresh tokens — store the new pair
    setTokens(data.access, data.refresh || refresh);
    return data.access;
}

async function _refreshAccessToken() {
    if (_refreshPromise) {
        return _refreshPromise;
    }
    _refreshPromise = _doRefresh().finally(() => { _refreshPromise = null; });
    return _refreshPromise;
}

// ---------------------------------------------------------------------------
// authFetch — authenticated fetch with auto-retry on 401
// ---------------------------------------------------------------------------

async function authFetch(url, options = {}) {
    const method = (options.method || 'GET').toUpperCase();
    const headers = Object.assign({}, options.headers || {});

    const token = getAccessToken();
    if (token) {
        headers['Authorization'] = 'Bearer ' + token;
    }
    if (method !== 'GET') {
        headers['X-CSRFToken'] = getCsrfToken();
        if (!headers['Content-Type']) {
            headers['Content-Type'] = 'application/json';
        }
    }

    let resp = await fetch(url, Object.assign({}, options, { headers }));

    // Auto-refresh on 401 and retry once
    if (resp.status === 401) {
        try {
            const newToken = await _refreshAccessToken();
            headers['Authorization'] = 'Bearer ' + newToken;
            resp = await fetch(url, Object.assign({}, options, { headers }));
        } catch (_) {
            clearTokens();
            window.location.href = '/login/';
            return resp;
        }
    }

    // If still 401 after refresh, clear and redirect
    if (resp.status === 401) {
        clearTokens();
        window.location.href = '/login/';
    }

    return resp;
}

// ---------------------------------------------------------------------------
// requireAuth — redirect to /login/ if no access token present
// ---------------------------------------------------------------------------

function requireAuth() {
    if (!getAccessToken()) {
        window.location.href = '/login/';
    }
}

// ---------------------------------------------------------------------------
// logout — blacklist refresh token then clear storage and redirect
// ---------------------------------------------------------------------------

async function logout() {
    const refresh = getRefreshToken();
    if (refresh) {
        try {
            await authFetch('/api/auth/logout/', {
                method: 'POST',
                body: JSON.stringify({ refresh }),
            });
        } catch (_) {
            // Best-effort; clear tokens regardless
        }
    }
    clearTokens();
    window.location.href = '/login/';
}

// ---------------------------------------------------------------------------
// Cross-tab logout — if another tab clears the access token, redirect here too
// ---------------------------------------------------------------------------

window.addEventListener('storage', function (e) {
    if (e.key === ACCESS_KEY && !e.newValue) {
        window.location.href = '/login/';
    }
});
