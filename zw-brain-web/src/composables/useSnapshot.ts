import { ref, computed } from 'vue';
import { authFetch } from './useAuth';

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
let _initialHydrated = false;

async function _fetchSnapshot(role: string): Promise<Snapshot> {
  const resp = await authFetch(`/api/snapshot?role=${encodeURIComponent(role)}`, {
    headers: { Accept: 'application/json' },
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return (await resp.json()) as Snapshot;
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
  try {
    const payload = await _fetchSnapshot(role);
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
