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
const _viewCache = new Map<string, WorkbenchView>();

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
      const resp = await authFetch(apiUrl(`/api/skills/workbench.view?role=${encodeURIComponent(role)}`), {
        headers: { Accept: 'application/json' },
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const payload = (await resp.json()) as WorkbenchView;
      if (!payload || typeof payload !== 'object' || !Array.isArray(payload.todos)) {
        throw new Error('payload shape unexpected');
      }
      _viewCache.set(role, payload);
      data.value = payload;
      source.value = 'live';
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
      data.value = WORKBENCH_FIXTURE;
      source.value = 'fixture';
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

  return { data, source, error, refresh };
}
