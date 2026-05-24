import { ref, onMounted, type Ref } from 'vue';
import { WORKBENCH_FIXTURE, type WorkbenchView } from '@/fixtures/workbench-fixture';
import { authFetch } from './useAuth';

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
export function useWorkbench(role = 'ROLE_ORGAN_OPERATER'): UseWorkbenchResult {
  const data = ref<WorkbenchView | null>(null);
  const source = ref<WorkbenchSource>('loading');
  const error = ref<string | null>(null);

  async function refresh(): Promise<void> {
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

  return { data, source, error, refresh };
}
