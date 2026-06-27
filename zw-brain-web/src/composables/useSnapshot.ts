import { ref, computed } from 'vue';
import { authFetch } from './useAuth';
import { apiUrl } from './useApiBase';

// 全量 snapshot 加载——对齐旧 js/app.js::refreshSnapshot()，把 /api/snapshot 返回的
// 各类 RUNTIME_* 暴露为响应式 ref，供 7 个 F2 占位页面读出基础计数 / 列表。
// F2 阶段只暴露读路径，不做局部刷新（那是 F3）。

export type Source = 'idle' | 'loading' | 'live' | 'fallback' | 'error';

export interface Snapshot {
  workbench: Record<string, unknown>;
  discovery: { resources?: unknown[] } & Record<string, unknown>;
  requests?: unknown[];
  approvals?: unknown[];
  delivery_tasks?: unknown[];
  provider?: Record<string, unknown>;
  disputes?: unknown[];
  zones?: unknown[];
  capability_packages?: unknown[];
  alerts?: unknown[];
  webui?: Record<string, unknown>;
  state?: Record<string, unknown>;
}

const _data = ref<Snapshot | null>(null);
const _source = ref<Source>('idle');
const _error = ref<string | null>(null);
const _cache = new Map<string, Snapshot>();
// FU-1 并发去重：同一 role 的在途请求合并到同一个 promise，boot/切角色/空闲预取
// 的并发触发不再放大成多次 /api/snapshot。settle 后清除。
const _inflight = new Map<string, Promise<Snapshot>>();
let _invalidationVersion = 0;
let _initialHydrated = false;

async function _fetchSnapshot(role: string): Promise<Snapshot> {
  const existing = _inflight.get(role);
  if (existing) return existing;
  const p = (async () => {
    const resp = await authFetch(apiUrl(`/api/snapshot?role=${encodeURIComponent(role)}`), {
      headers: { Accept: 'application/json' },
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return (await resp.json()) as Snapshot;
  })();
  _inflight.set(role, p);
  try {
    return await p;
  } finally {
    _inflight.delete(role);
  }
}

export async function loadSnapshot(
  role = 'ROLE_ORGAN_OPERATER',
  opts?: { soft?: boolean }
): Promise<Snapshot | null> {
  const soft = opts?.soft ?? _initialHydrated;
  const cached = _cache.get(role);
  if (cached) {
    _data.value = cached;
    _source.value = 'live';
  } else if (!soft) {
    _source.value = 'loading';
  }
  _error.value = null;
  const version = _invalidationVersion;
  try {
    const payload = await _fetchSnapshot(role);
    if (version !== _invalidationVersion) return null;
    _cache.set(role, payload);
    _data.value = payload;
    _source.value = 'live';
    _initialHydrated = true;
    return payload;
  } catch (e) {
    _error.value = e instanceof Error ? e.message : String(e);
    if (!cached) _source.value = 'error';
    _initialHydrated = true;
    return cached ?? null;
  }
}

// FU-3 写后失效：写能力成功后，受影响 role 的快照缓存作废，下次 loadSnapshot 拉新
// （不裸显陈旧数据）。无参=清全部。
export function invalidateSnapshot(role?: string): void {
  _invalidationVersion += 1;
  if (role) {
    _cache.delete(role);
    _inflight.delete(role);
  } else {
    _cache.clear();
    _inflight.clear();
  }
}

// FU-4 空闲预取：把某 role 的快照拉进缓存，**不触动**当前展示的 _data/_source/_error
// （后台静默，切到该岗位即命中缓存秒显）。复用 FU-1 在途合并，绝不与主动加载重复发请求。
export async function prefetchSnapshot(role: string): Promise<void> {
  if (_cache.has(role)) return;
  const version = _invalidationVersion;
  try {
    const payload = await _fetchSnapshot(role);
    if (version !== _invalidationVersion) return;
    _cache.set(role, payload);
  } catch {
    // 预取失败静默——主动切角色时 loadSnapshot 会正常重试并显错。
  }
}

export function useSnapshot() {
  return {
    data: computed(() => _data.value),
    source: computed(() => _source.value),
    error: computed(() => _error.value),
  };
}

export function useDiscoveryResources() {
  return computed(() => (_data.value?.discovery?.resources as unknown[] | undefined) ?? []);
}
export function useRequests() {
  return computed(() => (_data.value?.requests as unknown[] | undefined) ?? []);
}
export function useDeliveryTasks() {
  return computed(() => (_data.value?.delivery_tasks as unknown[] | undefined) ?? []);
}
export function useDisputes() {
  return computed(() => (_data.value?.disputes as unknown[] | undefined) ?? []);
}
export function useProvider() {
  return computed(() => (_data.value?.provider as Record<string, unknown> | undefined) ?? {});
}
export function useAlerts() {
  return computed(() => (_data.value?.alerts as unknown[] | undefined) ?? []);
}
export function useCapabilityPackages() {
  return computed(() => (_data.value?.capability_packages as unknown[] | undefined) ?? []);
}
export function useWebUiConfig() {
  return computed(() => (_data.value?.webui as Record<string, unknown> | undefined) ?? {});
}
export function useApprovals() {
  return computed(() => (_data.value?.approvals as unknown[] | undefined) ?? []);
}

function _findById(list: unknown[], id: string): Record<string, unknown> | null {
  for (const it of list) {
    const r = it as Record<string, unknown>;
    if (String(r.id ?? '') === id) return r;
  }
  return null;
}

export function lookupResource(id: string) {
  return computed(() => _findById((_data.value?.discovery?.resources as unknown[]) ?? [], id));
}
export function lookupRequest(id: string) {
  return computed(() => _findById((_data.value?.requests as unknown[]) ?? [], id));
}
export function lookupApproval(id: string) {
  return computed(() => _findById((_data.value?.approvals as unknown[]) ?? [], id));
}
export function lookupDeliveryTask(id: string) {
  return computed(() => _findById((_data.value?.delivery_tasks as unknown[]) ?? [], id));
}
export function lookupDispute(id: string) {
  return computed(() => _findById((_data.value?.disputes as unknown[]) ?? [], id));
}
