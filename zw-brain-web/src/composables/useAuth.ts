import { ref, computed } from 'vue';

// 与旧 js/auth.js BFF 模型对齐：
//   - access / refresh / id token 永远不到浏览器；BFF cookie 走 HttpOnly。
//   - sessionStorage 只存公共信息（user / csrf_token / expires_at / dev bypass 旗标）。
//   - 写请求带 X-CSRF-Token 头（双重提交防 CSRF）。
//
// F2 → F3：补 BroadcastChannel 多标签登出同步 + 5 分钟 refresh timer。
// 移植自旧 js/auth.js（保持模型不变：BFF cookie + sessionStorage 公共信息 + CSRF 双重提交）。

const STORAGE_KEY = 'zw-brain.auth.v1';
const CSRF_HEADER = 'X-CSRF-Token';
const BROADCAST_CHANNEL_NAME = 'zw-brain-auth';
const REFRESH_CHECK_MS = 5 * 60 * 1000;
const REFRESH_THRESHOLD_SECONDS = 60;
const PRODUCT_ROLE_CODES = [
  'ROLE_ORGAN_OPERATER',
  'ROLE_ORGAN_MANAGER',
  'ROLE_BUSIAUDIT',
  'ROLE_SECURITY_ADMIN',
  'ROLE_SECURITY_AUDIT',
  'ROLE_SYSTEM',
] as const;

let _refreshTimer: number | null = null;
let _broadcastChannel: BroadcastChannel | null = null;

export interface AuthUser {
  subject: string;
  username: string;
  displayName: string;
  email: string;
  orgCode: string;
  roles: string[];
  exp: number;
}

export interface AuthSnapshot {
  authenticated: boolean;
  development_iam_bypass: boolean;
  csrf_token: string;
  expires_at: number;
  actor_snapshot: Record<string, unknown>;
  claims: Record<string, unknown>;
  user: AuthUser | null;
}

const _state = ref<AuthSnapshot | null>(null);
const _loading = ref<boolean>(false);

function _readClaims(claims: unknown): Record<string, unknown> {
  return claims && typeof claims === 'object' ? (claims as Record<string, unknown>) : {};
}

function _userFromActor(actor: Record<string, unknown>, claims: Record<string, unknown>): AuthUser {
  const realmAccess = claims.realm_access as { roles?: string[] } | string[] | undefined;
  const realmRoles = Array.isArray(realmAccess)
    ? realmAccess
    : Array.isArray(realmAccess?.roles)
      ? (realmAccess?.roles ?? [])
      : [];
  const resourceRoles: string[] = [];
  const resAccess = claims.resource_access as Record<string, { roles?: string[] }> | undefined;
  if (resAccess && typeof resAccess === 'object') {
    Object.values(resAccess).forEach((it) => {
      if (Array.isArray(it?.roles)) resourceRoles.push(...it.roles);
    });
  }
  const actorRoles = Array.isArray(actor.role_codes) ? (actor.role_codes as string[]) : [];
  const roles = Array.from(new Set([...actorRoles, ...realmRoles, ...resourceRoles].map(String).filter(Boolean)));
  return {
    subject: String(claims.sub ?? actor.subject ?? ''),
    username: String(claims.preferred_username ?? actor.display_name ?? claims.sub ?? ''),
    displayName: String(actor.display_name ?? claims.preferred_username ?? claims.sub ?? '当前用户'),
    email: String(claims.email ?? ''),
    orgCode: String(claims.org_code ?? actor.org_code ?? ''),
    roles,
    exp: Number(claims.exp ?? 0),
  };
}

function _writeSnapshot(body: Record<string, unknown>): AuthSnapshot {
  const actor = (body.actor_snapshot ?? {}) as Record<string, unknown>;
  const claims = _readClaims(body.claims);
  const snapshot: AuthSnapshot = {
    authenticated: body.authenticated === true,
    development_iam_bypass: body.development_iam_bypass === true,
    csrf_token: String(body.csrf_token ?? ''),
    expires_at: Number(body.expires_at ?? 0),
    actor_snapshot: actor,
    claims,
    user: _userFromActor(actor, claims),
  };
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot));
  } catch (_) { /* ignore */ }
  _state.value = snapshot;
  return snapshot;
}

function _readLocalSnapshot(): AuthSnapshot | null {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as AuthSnapshot;
  } catch (_) {
    return null;
  }
}

function _clearSnapshot(): void {
  try {
    window.sessionStorage.removeItem(STORAGE_KEY);
  } catch (_) { /* ignore */ }
  _state.value = null;
}

async function _readJson(resp: Response): Promise<Record<string, unknown>> {
  let data: Record<string, unknown> = {};
  try {
    data = (await resp.json()) as Record<string, unknown>;
  } catch (_) { /* ignore */ }
  if (resp.ok) return data;
  const message = String(data.detail ?? data.error ?? `HTTP ${resp.status}`);
  throw Object.assign(new Error(message), { status: resp.status, payload: data });
}

async function _readAuthConfig(): Promise<{ development_iam_bypass_enabled?: boolean }> {
  const resp = await fetch('/auth/iaf/config', { headers: { Accept: 'application/json' }, credentials: 'include' });
  return (await _readJson(resp)) as { development_iam_bypass_enabled?: boolean };
}

async function _devBypassLogin(): Promise<AuthSnapshot> {
  const resp = await fetch('/auth/iaf/dev-bypass-login', {
    method: 'POST',
    headers: { Accept: 'application/json' },
    credentials: 'include',
  });
  const data = await _readJson(resp);
  return _writeSnapshot(data);
}

async function _readCurrentSession(): Promise<AuthSnapshot | null> {
  const resp = await fetch('/auth/iaf/session', { headers: { Accept: 'application/json' }, credentials: 'include' });
  if (resp.status === 401) return null;
  const data = await _readJson(resp);
  return _writeSnapshot(data);
}

export async function startLogin(): Promise<void> {
  const redirectUri = `${window.location.origin}/`;
  const resp = await fetch(`/auth/iaf/login?redirect_uri=${encodeURIComponent(redirectUri)}&format=json`, {
    headers: { Accept: 'application/json' },
    credentials: 'include',
  });
  const data = await _readJson(resp);
  const url = String(data.authorization_url ?? '');
  if (!url) throw new Error('授权地址缺失');
  window.location.href = url;
}

/** 顶栏「登录」唯一入口：dev bypass 走免登录，否则跳转 IAF/OIDC（与旧 ZW_AUTH.bootstrap 一致）。 */
export async function login(): Promise<AuthSnapshot | null> {
  const cfg = await _readAuthConfig().catch(() => ({ development_iam_bypass_enabled: false }));
  if (cfg.development_iam_bypass_enabled === true) {
    const snapshot = await _devBypassLogin();
    _broadcast('login');
    _startRefreshTimer();
    return snapshot;
  }
  await startLogin();
  return null;
}

export async function logout(): Promise<void> {
  const redirectUri = `${window.location.origin}/`;
  try {
    await fetch(`/auth/iaf/logout?redirect_uri=${encodeURIComponent(redirectUri)}`, {
      headers: { Accept: 'application/json' },
      credentials: 'include',
    });
  } catch (_) { /* ignore */ }
  _clearSnapshot();
  _stopRefreshTimer();
  _broadcast('logout');
  window.location.href = redirectUri;
}

function _openBroadcastChannel(): BroadcastChannel | null {
  if (_broadcastChannel) return _broadcastChannel;
  if (typeof window.BroadcastChannel !== 'function') return null;
  try {
    _broadcastChannel = new window.BroadcastChannel(BROADCAST_CHANNEL_NAME);
    _broadcastChannel.addEventListener('message', _handleBroadcastMessage);
  } catch (_) {
    _broadcastChannel = null;
  }
  return _broadcastChannel;
}

function _handleBroadcastMessage(event: MessageEvent): void {
  const data = event.data as { type?: string } | null;
  if (!data) return;
  if (data.type === 'logout') {
    _clearSnapshot();
    _stopRefreshTimer();
    window.location.reload();
  } else if (data.type === 'login') {
    void _readCurrentSession().then((s) => { if (s) _startRefreshTimer(); }).catch(() => undefined);
  }
}

function _broadcast(type: 'login' | 'logout'): void {
  const ch = _openBroadcastChannel();
  if (!ch) return;
  try { ch.postMessage({ type }); } catch (_) { /* ignore */ }
}

function _secondsUntilExpiry(s: AuthSnapshot | null): number {
  if (!s || !s.expires_at) return -1;
  return s.expires_at - Math.floor(Date.now() / 1000);
}

async function _refreshIfNeeded(force = false): Promise<AuthSnapshot | null> {
  const s = _state.value ?? _readLocalSnapshot();
  if (!s) return null;
  if (s.development_iam_bypass) return s;
  if (!force && _secondsUntilExpiry(s) >= REFRESH_THRESHOLD_SECONDS) return s;
  const csrf = s.csrf_token;
  if (!csrf) return s;
  try {
    const resp = await fetch('/auth/iaf/refresh', {
      method: 'POST',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json', [CSRF_HEADER]: csrf },
      credentials: 'include',
      body: '{}',
    });
    if (resp.status === 401) {
      _clearSnapshot();
      _stopRefreshTimer();
      return null;
    }
    const data = await _readJson(resp);
    return _writeSnapshot(data);
  } catch (_) {
    return s;
  }
}

function _startRefreshTimer(): void {
  _stopRefreshTimer();
  _refreshTimer = window.setInterval(() => {
    void _refreshIfNeeded(false).catch(() => _clearSnapshot());
  }, REFRESH_CHECK_MS);
}

function _stopRefreshTimer(): void {
  if (_refreshTimer !== null) {
    window.clearInterval(_refreshTimer);
    _refreshTimer = null;
  }
}

export async function bootstrap(): Promise<AuthSnapshot | null> {
  _loading.value = true;
  _openBroadcastChannel();
  try {
    let snapshot = _readLocalSnapshot();
    if (snapshot && (snapshot.expires_at === 0 || snapshot.expires_at * 1000 > Date.now())) {
      _state.value = snapshot;
      _startRefreshTimer();
      return snapshot;
    }
    snapshot = await _readCurrentSession().catch(() => null);
    if (snapshot && snapshot.authenticated) { _startRefreshTimer(); return snapshot; }
    const cfg = await _readAuthConfig().catch(() => ({ development_iam_bypass_enabled: false }));
    if (cfg.development_iam_bypass_enabled === true) {
      const s = await _devBypassLogin();
      _broadcast('login');
      _startRefreshTimer();
      return s;
    }
    return null;
  } finally {
    _loading.value = false;
  }
}

export async function authFetch(input: string, init?: RequestInit): Promise<Response> {
  const snapshot = _state.value ?? _readLocalSnapshot();
  const options: RequestInit = { ...(init ?? {}), credentials: 'include' };
  const headers = new Headers(options.headers ?? {});
  const method = String(options.method ?? 'GET').toUpperCase();
  if (method !== 'GET' && method !== 'HEAD' && snapshot?.csrf_token) {
    headers.set(CSRF_HEADER, String(snapshot.csrf_token));
  }
  options.headers = headers;
  const resp = await fetch(input, options);
  if (resp.status === 401) _clearSnapshot();
  return resp;
}

export function getCurrentUser() {
  return computed(() => _state.value?.user ?? null);
}

export function getSession() {
  return computed(() => _state.value);
}

export function getAllowedProductRoles(): string[] {
  const snapshot = _state.value;
  if (!snapshot) return [];
  if (snapshot.development_iam_bypass) return [...PRODUCT_ROLE_CODES];
  const actor = snapshot.actor_snapshot ?? {};
  const fromCtx = Array.isArray((actor as { available_contexts?: unknown }).available_contexts)
    ? ((actor as { available_contexts: { role_code?: string }[] }).available_contexts)
        .map((it) => String(it.role_code ?? ''))
        .filter((c) => (PRODUCT_ROLE_CODES as readonly string[]).includes(c))
    : [];
  if (fromCtx.length) return Array.from(new Set(fromCtx));
  const actorRoles = Array.isArray((actor as { role_codes?: unknown }).role_codes)
    ? ((actor as { role_codes: string[] }).role_codes).filter((c) => (PRODUCT_ROLE_CODES as readonly string[]).includes(c))
    : [];
  const userRoles = (snapshot.user?.roles ?? []).filter((c) => (PRODUCT_ROLE_CODES as readonly string[]).includes(c));
  return Array.from(new Set([...actorRoles, ...userRoles]));
}

export function isAuthLoading() {
  return computed(() => _loading.value);
}

export const PRODUCT_ROLE_LABELS: Record<string, string> = {
  ROLE_ORGAN_OPERATER: '部门操作员',
  ROLE_ORGAN_MANAGER: '部门管理员',
  ROLE_BUSIAUDIT: '业务运营员',
  ROLE_SECURITY_AUDIT: '安全审计员',
  ROLE_SECURITY_ADMIN: '安全管理员',
  ROLE_SYSTEM: '平台运维员',
};
