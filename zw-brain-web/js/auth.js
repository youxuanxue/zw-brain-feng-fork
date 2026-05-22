(function () {
  'use strict';

  // BFF session model:
  //   - access / refresh / id tokens never reach the browser; they live in the BFF session store
  //     and ride the HttpOnly session cookie the browser auto-sends.
  //   - sessionStorage keeps only public info: { authenticated, user, actor_snapshot, audit_id,
  //     csrf_token, expires_at, development_iam_bypass } so refresh + UI rendering work offline.
  //   - State-changing requests carry X-CSRF-Token (double-submit on the in-memory csrf_token).
  //   - Cross-tab login/logout sync goes through a BroadcastChannel that emits events only; no
  //     credentials are broadcast.

  const STORAGE_KEY = 'zw-brain.auth.v1';
  const CSRF_HEADER = 'X-CSRF-Token';
  const PRODUCT_ROLE_CODES = [
    'ROLE_ORGAN_OPERATER',
    'ROLE_ORGAN_MANAGER',
    'ROLE_BUSIAUDIT',
    'ROLE_SECURITY_ADMIN',
    'ROLE_SECURITY_AUDIT',
    'ROLE_SYSTEM',
  ];
  const REFRESH_CHECK_MS = 5 * 60 * 1000;
  const REFRESH_THRESHOLD_SECONDS = 60;
  const BROADCAST_CHANNEL_NAME = 'zw-brain-auth';
  let refreshTimer = null;
  let broadcastChannel = null;

  function openBroadcastChannel() {
    if (broadcastChannel) return broadcastChannel;
    if (typeof window.BroadcastChannel !== 'function') return null;
    try {
      broadcastChannel = new window.BroadcastChannel(BROADCAST_CHANNEL_NAME);
      broadcastChannel.addEventListener('message', handleBroadcastMessage);
    } catch (_) {
      broadcastChannel = null;
    }
    return broadcastChannel;
  }

  function handleBroadcastMessage(event) {
    const data = event && event.data;
    if (!data || typeof data !== 'object') return;
    if (data.type === 'logout') {
      clearLocalSnapshot();
      window.dispatchEvent(new CustomEvent('zw-auth-change', { detail: { authenticated: false, source: 'broadcast' } }));
      // Drop straight back to the login flow so other tabs don't keep stale UI on screen.
      window.location.reload();
    } else if (data.type === 'login') {
      // Another tab established a session — pull the public payload (incl. csrf_token) using the
      // shared cookie. Avoid window.location.reload(): a reload with empty sessionStorage would
      // re-enter startLogin() and create a duplicate session that overwrites the cookie.
      readCurrentSession().then((snapshot) => {
        if (snapshot) scheduleRefresh();
      }).catch(() => {});
    }
  }

  async function readCurrentSession() {
    const resp = await fetch('/auth/iaf/session', {
      headers: { Accept: 'application/json' },
      credentials: 'include',
    });
    if (resp.status === 401) return null;
    const data = await readJsonResponse(resp);
    return writeSnapshot(data);
  }

  function broadcastAuthEvent(type) {
    const channel = openBroadcastChannel();
    if (!channel) return;
    try {
      channel.postMessage({ type });
    } catch (_) {}
  }

  function readSnapshot() {
    try {
      const raw = window.sessionStorage.getItem(STORAGE_KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      return parsed && typeof parsed === 'object' ? parsed : null;
    } catch (_) {
      return null;
    }
  }

  function writeSnapshot(body) {
    const actor = body && body.actor_snapshot && typeof body.actor_snapshot === 'object' ? body.actor_snapshot : {};
    const claims = body && body.claims && typeof body.claims === 'object' ? body.claims : {};
    const snapshot = {
      authenticated: body && body.authenticated === true,
      development_iam_bypass: body && body.development_iam_bypass === true,
      csrf_token: String((body && body.csrf_token) || ''),
      expires_at: Number((body && body.expires_at) || 0),
      actor_snapshot: actor,
      claims,
      audit_id: String((body && body.audit_id) || ''),
      user: userFromActor(actor, claims),
      saved_at: Date.now(),
    };
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot));
    window.dispatchEvent(new CustomEvent('zw-auth-change', { detail: { authenticated: true } }));
    return snapshot;
  }

  function clearLocalSnapshot() {
    try {
      window.sessionStorage.removeItem(STORAGE_KEY);
    } catch (_) {}
  }

  function clearSession() {
    clearLocalSnapshot();
    window.dispatchEvent(new CustomEvent('zw-auth-change', { detail: { authenticated: false } }));
  }

  function userFromActor(actor, claims) {
    const safeActor = actor && typeof actor === 'object' ? actor : {};
    const safeClaims = claims && typeof claims === 'object' ? claims : {};
    const realmAccess = safeClaims.realm_access;
    const realmRoles = Array.isArray(realmAccess)
      ? realmAccess
      : realmAccess && typeof realmAccess === 'object' && Array.isArray(realmAccess.roles)
        ? realmAccess.roles
        : [];
    const resourceRoles = [];
    if (safeClaims.resource_access && typeof safeClaims.resource_access === 'object') {
      Object.values(safeClaims.resource_access).forEach(item => {
        if (item && typeof item === 'object' && Array.isArray(item.roles)) {
          item.roles.forEach(role => resourceRoles.push(role));
        }
      });
    }
    const roles = [...new Set([
      ...(safeActor.role_codes || []),
      ...realmRoles,
      ...resourceRoles,
    ].map(String).filter(Boolean))];
    return {
      subject: String(safeClaims.sub || safeActor.subject || ''),
      username: String(safeClaims.preferred_username || safeActor.display_name || safeClaims.sub || ''),
      displayName: String(safeActor.display_name || safeClaims.preferred_username || safeClaims.sub || '当前用户'),
      email: String(safeClaims.email || ''),
      phone: String(safeClaims.phone || ''),
      project: String(safeClaims.project || safeActor.project || ''),
      projectId: String(safeClaims.project_id || safeActor.project_id || safeActor.tenant_id || ''),
      orgCode: String(safeClaims.org_code || safeActor.org_code || ''),
      roles,
      exp: Number(safeClaims.exp || 0),
    };
  }

  function secondsUntilExpiry(snapshot) {
    const expiresAt = Number((snapshot && snapshot.expires_at) || 0);
    if (!expiresAt) return -1;
    return expiresAt - Math.floor(Date.now() / 1000);
  }

  function hasCodeInUrl() {
    const url = new URL(window.location.href);
    if (url.searchParams.get('code')) return true;
    const hash = window.location.hash || '';
    if (hash.includes('code=')) return true;
    return false;
  }

  function authCallbackParams() {
    const url = new URL(window.location.href);
    let code = url.searchParams.get('code') || '';
    let state = url.searchParams.get('state') || '';
    if ((!code || !state) && (window.location.hash || '').includes('code=')) {
      const raw = window.location.hash.startsWith('#') ? window.location.hash.slice(1) : window.location.hash;
      const parts = raw.startsWith('/') && raw.includes('?') ? raw.split('?', 2)[1] : raw;
      const params = new URLSearchParams(parts);
      code = code || params.get('code') || '';
      state = state || params.get('state') || '';
    }
    return { code, state };
  }

  function clearAuthCallbackParams() {
    const url = new URL(window.location.href);
    url.searchParams.delete('code');
    url.searchParams.delete('state');
    url.searchParams.delete('session_state');
    const hash = window.location.hash || '';
    const nextHash = hash.includes('code=') || hash.includes('state=') ? '#/workbench' : (hash || '#/workbench');
    window.history.replaceState(null, '', `${url.pathname}${url.search}${nextHash}`);
  }

  async function readJsonResponse(resp) {
    let data = {};
    try {
      data = await resp.json();
    } catch (_) {}
    if (resp.ok) return data;
    const err = new Error(data.detail || data.error || `HTTP ${resp.status}`);
    err.payload = data;
    err.status = resp.status;
    throw err;
  }

  async function readAuthConfig() {
    const resp = await fetch('/auth/iaf/config', {
      headers: { Accept: 'application/json' },
      credentials: 'include',
    });
    return readJsonResponse(resp);
  }

  async function startLogin() {
    const redirectUri = `${window.location.origin}/`;
    const resp = await fetch(`/auth/iaf/login?redirect_uri=${encodeURIComponent(redirectUri)}&format=json`, {
      headers: { Accept: 'application/json' },
      credentials: 'include',
    });
    const data = await readJsonResponse(resp);
    if (!data.authorization_url) throw new Error('当前服务未返回授权地址');
    window.location.href = String(data.authorization_url);
  }

  async function exchangeCodeForToken(code, state) {
    const resp = await fetch('/auth/iaf/token', {
      method: 'POST',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ code, state }),
    });
    const data = await readJsonResponse(resp);
    const snapshot = writeSnapshot(data);
    clearAuthCallbackParams();
    broadcastAuthEvent('login');
    return snapshot;
  }

  async function devBypassLogin() {
    const resp = await fetch('/auth/iaf/dev-bypass-login', {
      method: 'POST',
      headers: { Accept: 'application/json' },
      credentials: 'include',
    });
    const data = await readJsonResponse(resp);
    const snapshot = writeSnapshot(data);
    broadcastAuthEvent('login');
    return snapshot;
  }

  async function refreshTokenIfNeeded(force) {
    const snapshot = readSnapshot();
    if (!snapshot) return null;
    if (snapshot.development_iam_bypass === true) return snapshot;
    if (!force && secondsUntilExpiry(snapshot) >= REFRESH_THRESHOLD_SECONDS) return snapshot;
    const csrf = String(snapshot.csrf_token || '');
    if (!csrf) return snapshot;
    const resp = await fetch('/auth/iaf/refresh', {
      method: 'POST',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json', [CSRF_HEADER]: csrf },
      credentials: 'include',
      body: '{}',
    });
    if (resp.status === 401) {
      clearSession();
      return null;
    }
    const data = await readJsonResponse(resp);
    return writeSnapshot(data);
  }

  function scheduleRefresh() {
    if (refreshTimer) window.clearInterval(refreshTimer);
    refreshTimer = window.setInterval(() => {
      refreshTokenIfNeeded(false).catch(() => clearSession());
    }, REFRESH_CHECK_MS);
  }

  async function bootstrapAuth() {
    openBroadcastChannel();
    const params = authCallbackParams();
    if (params.code && params.state) {
      await exchangeCodeForToken(params.code, params.state);
      scheduleRefresh();
      return true;
    }
    let snapshot = readSnapshot();
    let authConfig = null;
    if (snapshot && secondsUntilExpiry(snapshot) > 0) {
      if (snapshot.development_iam_bypass !== true) {
        scheduleRefresh();
        return true;
      }
      authConfig = await readAuthConfig();
      if (authConfig.development_iam_bypass_enabled === true) {
        scheduleRefresh();
        return true;
      }
    }
    clearLocalSnapshot();
    // A new tab inherits the BFF cookie but starts with empty sessionStorage. Try to bootstrap
    // the public snapshot (csrf_token, user, expiry) from the existing server session before
    // falling back to a fresh login — otherwise we'd create a duplicate session and orphan the
    // first tab's csrf_token.
    try {
      snapshot = await readCurrentSession();
    } catch (_) {
      snapshot = null;
    }
    if (snapshot && secondsUntilExpiry(snapshot) > 0) {
      scheduleRefresh();
      return true;
    }
    authConfig = authConfig || await readAuthConfig();
    if (authConfig.development_iam_bypass_enabled === true) {
      await devBypassLogin();
      scheduleRefresh();
      return true;
    }
    if (!hasCodeInUrl()) await startLogin();
    return false;
  }

  async function authFetch(input, init) {
    await refreshTokenIfNeeded(false);
    let snapshot = readSnapshot();
    if (snapshot && snapshot.development_iam_bypass === true && secondsUntilExpiry(snapshot) <= 0) {
      clearLocalSnapshot();
      const authConfig = await readAuthConfig();
      if (authConfig.development_iam_bypass_enabled === true) {
        snapshot = await devBypassLogin();
      } else {
        await startLogin();
        throw new Error('未登录或登录已过期');
      }
    }
    if (!snapshot) {
      await startLogin();
      throw new Error('未登录或登录已过期');
    }
    const options = Object.assign({}, init || {});
    options.credentials = 'include';
    const headers = new Headers(options.headers || {});
    const method = String(options.method || 'GET').toUpperCase();
    if (method !== 'GET' && method !== 'HEAD') {
      const csrf = String(snapshot.csrf_token || '');
      if (csrf) headers.set(CSRF_HEADER, csrf);
    }
    options.headers = headers;
    const resp = await fetch(input, options);
    if (resp.status === 401) {
      clearSession();
    } else if (resp.status === 403) {
      // CSRF mismatch typically means another tab's login overwrote our cookie+csrf pairing.
      // Drop the local snapshot so the next bootstrap re-fetches /auth/iaf/session and recovers.
      // Clone so the caller still sees the original response body.
      const probe = await resp.clone().json().catch(() => null);
      if (probe && probe.error === 'csrf_token_invalid') {
        clearSession();
      }
    }
    return resp;
  }

  async function logout() {
    const snapshot = readSnapshot();
    const redirectUri = `${window.location.origin}/`;
    if (snapshot && snapshot.development_iam_bypass === true) {
      // Bypass logout is a local cleanup; still hit the server so the BFF session is dropped.
      try {
        await fetch(`/auth/iaf/logout?redirect_uri=${encodeURIComponent(redirectUri)}`, {
          headers: { Accept: 'application/json' },
          credentials: 'include',
        });
      } catch (_) {}
      clearSession();
      broadcastAuthEvent('logout');
      window.location.href = redirectUri;
      return;
    }
    const params = new URLSearchParams({ redirect_uri: redirectUri });
    const resp = await fetch(`/auth/iaf/logout?${params.toString()}`, {
      headers: { Accept: 'application/json' },
      credentials: 'include',
    });
    const data = await readJsonResponse(resp);
    clearSession();
    broadcastAuthEvent('logout');
    window.location.href = data.logout_url || redirectUri;
  }

  function getCurrentUser() {
    const snapshot = readSnapshot();
    return snapshot && snapshot.user ? snapshot.user : null;
  }

  function getSession() {
    return readSnapshot();
  }

  /** 会话内可切换的产品岗位（available_contexts / role_codes；dev bypass 为全部 6 岗） */
  function getAllowedProductRoles() {
    const snapshot = readSnapshot();
    if (!snapshot) return [];
    if (snapshot.development_iam_bypass === true) {
      return PRODUCT_ROLE_CODES.slice();
    }
    const actor = snapshot.actor_snapshot && typeof snapshot.actor_snapshot === 'object' ? snapshot.actor_snapshot : {};
    const fromContexts = Array.isArray(actor.available_contexts)
      ? actor.available_contexts
          .map(item => String((item && item.role_code) || ''))
          .filter(code => PRODUCT_ROLE_CODES.includes(code))
      : [];
    if (fromContexts.length) {
      return [...new Set(fromContexts)];
    }
    const fromActor = (actor.role_codes || []).map(String).filter(code => PRODUCT_ROLE_CODES.includes(code));
    const fromUser = snapshot.user && Array.isArray(snapshot.user.roles)
      ? snapshot.user.roles.map(String).filter(code => PRODUCT_ROLE_CODES.includes(code))
      : [];
    return [...new Set([...fromActor, ...fromUser])];
  }

  function isProductRoleAllowed(role) {
    const code = String(role || '');
    if (!PRODUCT_ROLE_CODES.includes(code)) return false;
    const allowed = getAllowedProductRoles();
    if (!allowed.length) return false;
    return allowed.includes(code);
  }

  window.ZW_AUTH = {
    bootstrapAuth,
    startLogin,
    exchangeCodeForToken,
    refreshTokenIfNeeded,
    authFetch,
    logout,
    getCurrentUser,
    getSession,
    clearSession,
    getAllowedProductRoles,
    isProductRoleAllowed,
  };
})();
