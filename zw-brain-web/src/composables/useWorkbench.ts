import { ref, onMounted, watch, type Ref } from 'vue';
import { WORKBENCH_FIXTURE, type WorkbenchView } from '@/fixtures/workbench-fixture';
import { authFetch, getSession, hasAllowedProductRoles } from './useAuth';
import { getProductRole } from './useProductRole';
import { apiUrl } from './useApiBase';

export type WorkbenchSource = 'live' | 'fixture' | 'loading';

export interface UseWorkbenchResult {
  data: Ref<WorkbenchView | null>;
  source: Ref<WorkbenchSource>;
  error: Ref<string | null>;
  refresh: () => Promise<void>;
}

// 调用 brain REST 入口 /api/skills/workbench.view （POST）。
// 失败回落到本地 fixture，并把 source 标成 'fixture'，让 UI 上面挂个开发期提示条。
//
// F1 spike 阶段 brain server 通常未起 → 直接 fixture 路径。F2 起接入认证后改成默认 live。
// 反馈（0604 二轮走查，负责人）：「加载时间有点长」。两处根因：
//   1) 挂载时 auth 仍在 bootstrap → refresh 早退停在 loading，且无任何 watch 在
//      auth 就绪后补触发（只有切岗位才救活）——竞态下工作台可长挂「正在加载」。
//   2) 每次导航回工作台都重新拉取——无缓存，重复看 loading 闪烁。
// 修法：watch(session) 就绪即补触发 + 模块级按岗位 SWR 缓存（先显缓存、后台刷新）。
//
// #213 follow-up（本 PR）：把拉取下沉为模块级、加并发去重 + 预取 + 写后失效——
//   FU-1 _inflight 在途合并；FU-4 prefetchWorkbench 静默填缓存；FU-3 invalidateWorkbench
//   作废缓存并经 _invalidationTick 通知已挂载实例重拉（写后待办不再陈旧）。
const _viewCache = new Map<string, WorkbenchView>();
const _inflight = new Map<string, Promise<WorkbenchView>>();
// 写后失效信号：bump 后所有已挂载的 useWorkbench 实例重拉（覆盖 P1 工作台等）。
const _invalidationTick = ref(0);

/** 模块级拉取 + FU-1 并发去重：同 role 在途请求复用同一 promise，settle 后清除。 */
async function fetchWorkbenchView(role: string): Promise<WorkbenchView> {
  const existing = _inflight.get(role);
  if (existing) return existing;
  const p = (async () => {
    const resp = await authFetch(
      apiUrl(`/api/skills/workbench.view?role=${encodeURIComponent(role)}`),
      { headers: { Accept: 'application/json' } },
    );
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const payload = (await resp.json()) as WorkbenchView;
    if (!payload || typeof payload !== 'object' || !Array.isArray(payload.todos)) {
      throw new Error('payload shape unexpected');
    }
    return payload;
  })();
  _inflight.set(role, p);
  try {
    return await p;
  } finally {
    _inflight.delete(role);
  }
}

// FU-4 空闲预取：把某 role 的工作台拉进缓存，不触动任何已挂载实例的展示态。
export async function prefetchWorkbench(role: string): Promise<void> {
  if (_viewCache.has(role)) return;
  try {
    _viewCache.set(role, await fetchWorkbenchView(role));
  } catch {
    // 预取失败静默——主动进工作台时 refresh() 会正常重试并回落 fixture/显错。
  }
}

// FU-3 写后失效：作废受影响 role 的工作台缓存，并通知已挂载实例重拉（无参=清全部）。
export function invalidateWorkbench(role?: string): void {
  if (role) _viewCache.delete(role);
  else _viewCache.clear();
  _invalidationTick.value += 1;
}

export function useWorkbench(roleOverride?: string): UseWorkbenchResult {
  const data = ref<WorkbenchView | null>(null);
  const source = ref<WorkbenchSource>('loading');
  const error = ref<string | null>(null);
  const session = getSession();

  function resolveRole(): string {
    return roleOverride ?? getProductRole().value;
  }

  async function refresh(): Promise<void> {
    if (!hasAllowedProductRoles()) {
      source.value = 'loading';
      error.value = null;
      data.value = null;
      return;
    }
    const role = resolveRole();
    // SWR：有缓存先即时呈现（live），后台静默刷新替换；无缓存才显 loading。
    const cached = _viewCache.get(role);
    if (cached) {
      data.value = cached;
      source.value = 'live';
    } else {
      source.value = 'loading';
    }
    error.value = null;
    try {
      const payload = await fetchWorkbenchView(role);
      _viewCache.set(role, payload);
      data.value = payload;
      source.value = 'live';
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
      // 仅在无缓存可显时回落 fixture；有缓存则保留 SWR 旧值不闪 fixture。
      if (!cached) {
        data.value = WORKBENCH_FIXTURE;
        source.value = 'fixture';
      }
    }
  }

  onMounted(() => {
    void refresh();
  });

  if (!roleOverride) {
    watch(getProductRole(), () => {
      void refresh();
    });
  }
  // auth bootstrap 完成（session 从 null → 就绪）后补触发，消除挂载竞态。
  watch(session, (snap, prev) => {
    if (snap && !prev) void refresh();
  });
  // FU-3：写后失效信号 → 重拉（缓存已被作废，必拉新）。
  watch(_invalidationTick, () => {
    void refresh();
  });

  return { data, source, error, refresh };
}
