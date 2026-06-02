import { ref, computed } from 'vue';
import { setProductRole } from './useProductRole';
import { apiUrl, appOrigin } from './useApiBase';

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
// 任何业务 fetch 上限 15s：超时 → AbortError → 上层 composable catch → fixture/error toast。
// 唯一 chokepoint，避免 17+ composable 各自补 timeout。escape hatch：调用方传
// init.signal=null 显式禁用（当前无 long-poll/SSE 场景）。
export const DEFAULT_FETCH_TIMEOUT_MS = 15_000;
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
let _bootstrapInFlight: Promise<AuthSnapshot | null> | null = null;

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
  syncProductRoleFromSession();
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
  const resp = await fetch(apiUrl('/auth/iaf/config'), { headers: { Accept: 'application/json' }, credentials: 'include' });
  return (await _readJson(resp)) as { development_iam_bypass_enabled?: boolean };
}

async function _devBypassLogin(): Promise<AuthSnapshot> {
  const resp = await fetch(apiUrl('/auth/iaf/dev-bypass-login'), {
    method: 'POST',
    headers: { Accept: 'application/json' },
    credentials: 'include',
  });
  const data = await _readJson(resp);
  return _writeSnapshot(data);
}

async function _readCurrentSession(): Promise<AuthSnapshot | null> {
  const resp = await fetch(apiUrl('/auth/iaf/session'), { headers: { Accept: 'application/json' }, credentials: 'include' });
  if (resp.status === 401) return null;
  const data = await _readJson(resp);
  return _writeSnapshot(data);
}

export async function startLogin(): Promise<void> {
  const redirectUri = appOrigin();
  const resp = await fetch(apiUrl(`/auth/iaf/login?redirect_uri=${encodeURIComponent(redirectUri)}&format=json`), {
    headers: { Accept: 'application/json' },
    credentials: 'include',
  });
  const data = await _readJson(resp);
  const url = String(data.authorization_url ?? '');
  if (!url) throw new Error('授权地址缺失');
  window.location.href = url;
}

export async function loginWithIam(): Promise<void> {
  await startLogin();
}

export async function loginWithDevBypass(): Promise<AuthSnapshot> {
  const cfg = await _readAuthConfig().catch(() => ({ development_iam_bypass_enabled: false }));
  if (cfg.development_iam_bypass_enabled !== true) {
    throw new Error('当前环境未启用开发免登录');
  }
  const snapshot = await _devBypassLogin();
  _broadcast('login');
  _startRefreshTimer();
  return snapshot;
}

/** 兼容旧调用：默认走统一身份登录，不再自动选择开发 bypass。 */
export async function login(): Promise<AuthSnapshot | null> {
  await loginWithIam();
  return null;
}

export async function logout(): Promise<void> {
  const redirectUri = appOrigin();
  let logoutUrl = redirectUri;
  try {
    const resp = await fetch(apiUrl(`/auth/iaf/logout?redirect_uri=${encodeURIComponent(redirectUri)}`), {
      headers: { Accept: 'application/json' },
      credentials: 'include',
    });
    let data: Record<string, unknown> = {};
    try {
      data = (await resp.json()) as Record<string, unknown>;
    } catch (_) { /* ignore */ }
    if (resp.ok && data.logout_url) {
      logoutUrl = String(data.logout_url);
    }
  } catch (_) { /* ignore */ }
  _clearSnapshot();
  _stopRefreshTimer();
  _broadcast('logout');
  // 必须跳转 IAM logout_url 清除 SSO 会话；仅回本地页会导致下次统一身份登录免密复用旧账号。
  window.location.href = logoutUrl;
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
    const resp = await fetch(apiUrl('/auth/iaf/refresh'), {
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

function _oauthParamsFromUrl(): { code: string; state: string } | null {
  const fromSearch = new URLSearchParams(window.location.search);
  const code = fromSearch.get('code');
  const state = fromSearch.get('state');
  if (code && state) return { code, state };
  const hash = window.location.hash;
  const qIdx = hash.indexOf('?');
  if (qIdx < 0) return null;
  const fromHash = new URLSearchParams(hash.slice(qIdx + 1));
  const hashCode = fromHash.get('code');
  const hashState = fromHash.get('state');
  if (hashCode && hashState) return { code: hashCode, state: hashState };
  return null;
}

function _stripOAuthParamsFromUrl(): void {
  const url = new URL(window.location.href);
  for (const key of ['code', 'state', 'session_state']) {
    url.searchParams.delete(key);
  }
  if (url.hash.includes('?')) {
    const [hashPath, hashQuery] = url.hash.split('?');
    const hp = new URLSearchParams(hashQuery ?? '');
    for (const key of ['code', 'state', 'session_state']) {
      hp.delete(key);
    }
    const rest = hp.toString();
    url.hash = rest ? `${hashPath}?${rest}` : hashPath;
  }
  const next = `${url.pathname}${url.search}${url.hash}`;
  window.history.replaceState({}, document.title, next);
}

export async function exchangeCodeForToken(code: string, state: string): Promise<AuthSnapshot> {
  const resp = await fetch(apiUrl('/auth/iaf/token'), {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ code, state }),
  });
  const data = await _readJson(resp);
  return _writeSnapshot(data);
}

export function hasPendingOAuthCallback(): boolean {
  return _oauthParamsFromUrl() !== null;
}

async function _completeOAuthCallback(oauth: { code: string; state: string }): Promise<AuthSnapshot> {
  try {
    const snapshot = await exchangeCodeForToken(oauth.code, oauth.state);
    _broadcast('login');
    _startRefreshTimer();
    return snapshot;
  } finally {
    // 无论换票成功或失败都剥离 URL 中的 code/state，避免授权码被二次提交触发 IAF HTTP 400。
    _stripOAuthParamsFromUrl();
  }
}

async function _runBootstrap(): Promise<AuthSnapshot | null> {
  _loading.value = true;
  _openBroadcastChannel();
  try {
    const oauth = _oauthParamsFromUrl();
    if (oauth) {
      return await _completeOAuthCallback(oauth);
    }
    let snapshot = _readLocalSnapshot();
    if (snapshot && (snapshot.expires_at === 0 || snapshot.expires_at * 1000 > Date.now())) {
      _state.value = snapshot;
      _startRefreshTimer();
      return snapshot;
    }
    snapshot = await _readCurrentSession().catch(() => null);
    if (snapshot && snapshot.authenticated) { _startRefreshTimer(); return snapshot; }
    return null;
  } finally {
    _loading.value = false;
  }
}

export async function bootstrap(): Promise<AuthSnapshot | null> {
  if (!_bootstrapInFlight) {
    _bootstrapInFlight = _runBootstrap().finally(() => {
      _bootstrapInFlight = null;
    });
  }
  return _bootstrapInFlight;
}

export async function waitForAuthBootstrap(): Promise<void> {
  if (_bootstrapInFlight) {
    await _bootstrapInFlight.catch(() => null);
  }
}

export async function authFetch(input: string, init?: RequestInit): Promise<Response> {
  await waitForAuthBootstrap();
  const snapshot = _state.value ?? _readLocalSnapshot();
  const options: RequestInit = { ...(init ?? {}), credentials: 'include' };
  const headers = new Headers(options.headers ?? {});
  const method = String(options.method ?? 'GET').toUpperCase();
  if (method !== 'GET' && method !== 'HEAD' && snapshot?.csrf_token) {
    headers.set(CSRF_HEADER, String(snapshot.csrf_token));
  }
  options.headers = headers;
  // 注入 DEFAULT_FETCH_TIMEOUT_MS 上限；与调用方自带 signal 合并（任一中断即整体中断）。
  // init.signal === null 时显式跳过 timeout（escape hatch，预留给未来 long-poll/SSE）。
  if (init?.signal !== null) {
    const timeoutSignal = AbortSignal.timeout(DEFAULT_FETCH_TIMEOUT_MS);
    options.signal = init?.signal
      ? AbortSignal.any([init.signal, timeoutSignal])
      : timeoutSignal;
  } else {
    delete options.signal;
  }
  const resp = await fetch(input, options);
  if (resp.status === 401 && snapshot?.authenticated) _clearSnapshot();
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
  return _allowedProductRolesFromSnapshot(snapshot);
}

/** 当前会话是否具备至少一个可用产品岗位（开发 bypass 始终视为有）。 */
export function hasAllowedProductRoles(): boolean {
  const snapshot = _state.value;
  if (!snapshot?.authenticated) return false;
  // dev-bypass 不再 blanket-true：必须看真实 actor.role_codes，否则
  // ZW_BRAIN_DEV_IAM_BYPASS_ROLES="" 重现 A3 时，前端会假装用户有岗位
  // 而后端 403 — UX 错位。改为统一从 snapshot 派生。
  return _allowedProductRolesFromSnapshot(snapshot).length > 0;
}

function _allowedProductRolesFromSnapshot(snapshot: AuthSnapshot): string[] {
  const actor = snapshot.actor_snapshot ?? {};
  const fromCtx = Array.isArray((actor as { available_contexts?: unknown }).available_contexts)
    ? ((actor as { available_contexts: { role_code?: string }[] }).available_contexts)
        .map((it) => String(it.role_code ?? ''))
        .filter((c) => (PRODUCT_ROLE_CODES as readonly string[]).includes(c))
    : [];
  const actorRoles = Array.isArray((actor as { role_codes?: unknown }).role_codes)
    ? ((actor as { role_codes: string[] }).role_codes).filter((c) => (PRODUCT_ROLE_CODES as readonly string[]).includes(c))
    : [];
  const userRoles = (snapshot.user?.roles ?? []).filter((c) => (PRODUCT_ROLE_CODES as readonly string[]).includes(c));
  const sessionRole = String((actor as { current_role?: string }).current_role ?? '');
  const roles = [...fromCtx, ...actorRoles, ...userRoles];
  if (sessionRole && (PRODUCT_ROLE_CODES as readonly string[]).includes(sessionRole)) {
    roles.push(sessionRole);
  }
  return Array.from(new Set(roles));
}

/** 登录后会话 actor_snapshot.current_role → 顶栏岗位与路由守卫。 */
export function syncProductRoleFromSession(): void {
  const snapshot = _state.value;
  if (!snapshot?.authenticated) return;
  const roles = _allowedProductRolesFromSnapshot(snapshot);
  const actor = snapshot.actor_snapshot ?? {};
  const sessionRole = String((actor as { current_role?: string }).current_role ?? '');
  if (sessionRole && roles.includes(sessionRole)) {
    setProductRole(sessionRole);
    return;
  }
  if (roles.length) setProductRole(roles[0]);
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
