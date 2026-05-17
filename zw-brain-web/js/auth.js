(function () {
  'use strict';

  const STORAGE_KEY = 'zw-brain.auth.v1';
  const REFRESH_CHECK_MS = 5 * 60 * 1000;
  const REFRESH_THRESHOLD_SECONDS = 60;
  let refreshTimer = null;

  function readSession() {
    try {
      const raw = window.sessionStorage.getItem(STORAGE_KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      return parsed && typeof parsed === 'object' ? parsed : null;
    } catch (_) {
      return null;
    }
  }

  function writeSession(session) {
    const accessClaims = safeDecodeJwtPayload(session.access_token || '');
    const next = Object.assign({}, session, {
      claims: accessClaims,
      user: userFromClaims(accessClaims, session.actor_snapshot || null),
      saved_at: Date.now(),
    });
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    window.dispatchEvent(new CustomEvent('zw-auth-change', { detail: { authenticated: true } }));
    return next;
  }

  function clearSession() {
    try {
      window.sessionStorage.removeItem(STORAGE_KEY);
    } catch (_) {}
    window.dispatchEvent(new CustomEvent('zw-auth-change', { detail: { authenticated: false } }));
  }

  function safeDecodeJwtPayload(token) {
    const parts = String(token || '').split('.');
    if (parts.length !== 3 || !parts[1]) return {};
    try {
      let payload = parts[1].replace(/-/g, '+').replace(/_/g, '/');
      payload += '='.repeat((4 - payload.length % 4) % 4);
      const decoded = JSON.parse(window.atob(payload));
      return decoded && typeof decoded === 'object' ? decoded : {};
    } catch (_) {
      return {};
    }
  }

  function userFromClaims(claims, actorSnapshot) {
    const actor = actorSnapshot && typeof actorSnapshot === 'object' ? actorSnapshot : {};
    const realmAccess = claims.realm_access;
    const realmRoles = Array.isArray(realmAccess)
      ? realmAccess
      : realmAccess && typeof realmAccess === 'object' && Array.isArray(realmAccess.roles)
        ? realmAccess.roles
        : [];
    const resourceRoles = [];
    if (claims.resource_access && typeof claims.resource_access === 'object') {
      Object.values(claims.resource_access).forEach(item => {
        if (item && typeof item === 'object' && Array.isArray(item.roles)) {
          item.roles.forEach(role => resourceRoles.push(role));
        }
      });
    }
    const roles = [...new Set([...(actor.role_codes || []), ...realmRoles, ...resourceRoles].map(String).filter(Boolean))];
    return {
      subject: String(claims.sub || actor.subject || ''),
      username: String(claims.preferred_username || actor.display_name || claims.sub || ''),
      displayName: String(actor.display_name || claims.preferred_username || claims.sub || '当前用户'),
      email: String(claims.email || ''),
      phone: String(claims.phone || ''),
      project: String(claims.project || actor.project || ''),
      projectId: String(claims.project_id || actor.project_id || ''),
      orgCode: String(claims.org_code || actor.org_code || ''),
      roles,
      exp: Number(claims.exp || 0),
    };
  }

  function tokenSecondsLeft(session) {
    const exp = Number((session && session.claims && session.claims.exp) || 0);
    if (!exp) return -1;
    return exp - Math.floor(Date.now() / 1000);
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
    const nextHash = hash.includes('code=') || hash.includes('state=') ? '#/p1-workbench' : (hash || '#/p1-workbench');
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
    });
    return readJsonResponse(resp);
  }

  function writeDevelopmentIamBypassSession(authConfig) {
    // Identity comes from /auth/iaf/config, which is the single source of truth for the synthetic
    // bypass user. The frontend no longer hardcodes role lists — server changes propagate automatically.
    const profile = (authConfig && authConfig.development_iam_bypass_user) || {};
    const roles = Array.isArray(profile.role_codes) ? profile.role_codes.map(String).filter(Boolean) : [];
    const subject = String(profile.subject || 'dev-iam-bypass');
    const username = String(profile.username || 'dev_iam_bypass');
    const tenantId = String(profile.tenant_id || 'sd-default');
    const orgCode = String(profile.org_code || 'dev');
    const displayName = String(profile.display_name || username);
    const nowSeconds = Math.floor(Date.now() / 1000);
    const session = {
      authenticated: true,
      development_iam_bypass: true,
      access_token: '',
      claims: {
        sub: subject,
        preferred_username: username,
        project_id: tenantId,
        org_code: orgCode,
        development_iam_bypass: true,
        exp: nowSeconds + 24 * 60 * 60,
      },
      user: {
        subject,
        username,
        displayName,
        email: '',
        phone: '',
        project: '',
        projectId: tenantId,
        orgCode,
        roles,
        exp: nowSeconds + 24 * 60 * 60,
      },
      saved_at: Date.now(),
    };
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
    window.dispatchEvent(new CustomEvent('zw-auth-change', { detail: { authenticated: true, development_iam_bypass: true } }));
    return session;
  }

  async function startLogin() {
    const redirectUri = `${window.location.origin}/`;
    const resp = await fetch(`/auth/iaf/login?redirect_uri=${encodeURIComponent(redirectUri)}&format=json`, {
      headers: { Accept: 'application/json' },
    });
    const data = await readJsonResponse(resp);
    if (!data.authorization_url) throw new Error('当前服务未返回授权地址');
    window.location.href = String(data.authorization_url);
  }

  async function exchangeCodeForToken(code, state) {
    const resp = await fetch('/auth/iaf/token', {
      method: 'POST',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, state }),
    });
    const data = await readJsonResponse(resp);
    writeSession(data);
    clearAuthCallbackParams();
    return data;
  }

  async function refreshTokenIfNeeded(force) {
    const session = readSession();
    if (!session || !session.refresh_token) return null;
    if (!force && tokenSecondsLeft(session) >= REFRESH_THRESHOLD_SECONDS) return session;
    const resp = await fetch('/auth/iaf/refresh', {
      method: 'POST',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: session.refresh_token }),
    });
    const data = await readJsonResponse(resp);
    return writeSession(Object.assign({}, session, data, { actor_snapshot: session.actor_snapshot }));
  }

  function scheduleRefresh() {
    if (refreshTimer) window.clearInterval(refreshTimer);
    refreshTimer = window.setInterval(() => {
      refreshTokenIfNeeded(false).catch(() => clearSession());
    }, REFRESH_CHECK_MS);
  }

  async function bootstrapAuth() {
    const params = authCallbackParams();
    if (params.code && params.state) {
      await exchangeCodeForToken(params.code, params.state);
      scheduleRefresh();
      return true;
    }
    const session = readSession();
    let authConfig = null;
    if (session && tokenSecondsLeft(session) > 0) {
      if (session.development_iam_bypass !== true) {
        scheduleRefresh();
        return true;
      }
      authConfig = await readAuthConfig();
      if (authConfig.development_iam_bypass_enabled === true) {
        scheduleRefresh();
        return true;
      }
    }
    clearSession();
    authConfig = authConfig || await readAuthConfig();
    if (authConfig.development_iam_bypass_enabled === true) {
      writeDevelopmentIamBypassSession(authConfig);
      scheduleRefresh();
      return true;
    }
    if (!hasCodeInUrl()) await startLogin();
    return false;
  }

  async function authFetch(input, init) {
    await refreshTokenIfNeeded(false);
    let session = readSession();
    if (session && session.development_iam_bypass === true && tokenSecondsLeft(session) <= 0) {
      clearSession();
      const authConfig = await readAuthConfig();
      if (authConfig.development_iam_bypass_enabled === true) {
        session = writeDevelopmentIamBypassSession(authConfig);
      } else {
        await startLogin();
        throw new Error('未登录或登录已过期');
      }
    }
    if (!session || (!session.access_token && session.development_iam_bypass !== true)) {
      await startLogin();
      throw new Error('未登录或登录已过期');
    }
    const options = Object.assign({}, init || {});
    const headers = new Headers(options.headers || {});
    if (session.development_iam_bypass !== true) {
      headers.set('Authorization', `Bearer ${session.access_token}`);
    }
    options.headers = headers;
    const resp = await fetch(input, options);
    if (resp.status === 401) {
      clearSession();
    }
    return resp;
  }

  async function logout() {
    const session = readSession();
    clearSession();
    const redirectUri = `${window.location.origin}/`;
    if (session && session.development_iam_bypass === true) {
      window.location.href = redirectUri;
      return;
    }
    // Pass id_token_hint when we have it — without it the IAM gateway may prompt the user before
    // honoring post_logout_redirect_uri.
    const params = new URLSearchParams({ redirect_uri: redirectUri });
    const idToken = session && session.id_token ? String(session.id_token) : '';
    if (idToken) params.set('id_token_hint', idToken);
    const resp = await fetch(`/auth/iaf/logout?${params.toString()}`, {
      headers: { Accept: 'application/json' },
    });
    const data = await readJsonResponse(resp);
    window.location.href = data.logout_url || redirectUri;
  }

  function getCurrentUser() {
    const session = readSession();
    return session && session.user ? session.user : null;
  }

  function getSession() {
    return readSession();
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
    safeDecodeJwtPayload,
    clearSession,
  };
})();
