import { ref, onMounted, watch, type Ref } from 'vue';
import { WORKBENCH_FIXTURE, type WorkbenchView } from '@/fixtures/workbench-fixture';
import { authFetch, hasAllowedProductRoles } from './useAuth';
import { getProductRole } from './useProductRole';

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
export function useWorkbench(roleOverride?: string): UseWorkbenchResult {
  const data = ref<WorkbenchView | null>(null);
  const source = ref<WorkbenchSource>('loading');
  const error = ref<string | null>(null);

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
    source.value = 'loading';
    error.value = null;
    try {
      const resp = await authFetch(`/api/skills/workbench.view?role=${encodeURIComponent(role)}`, {
        headers: { Accept: 'application/json' },
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const payload = (await resp.json()) as WorkbenchView;
      if (!payload || typeof payload !== 'object' || !Array.isArray(payload.todos)) {
        throw new Error('payload shape unexpected');
      }
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

  return { data, source, error, refresh };
}
