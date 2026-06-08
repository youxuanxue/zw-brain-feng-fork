import { computed, ref, watch } from 'vue';
import { authFetch } from './useAuth';
import { apiUrl } from './useApiBase';

/** 资源详情：始终从 API 拉取完整详情（0605#2：不再先用 snapshot 缩略信息首刷，消除视觉跳跃感）。 */
export function useResourceDetail(resourceId: () => string, role = 'ROLE_ORGAN_OPERATER') {
  const fetched = ref<Record<string, unknown> | null>(null);
  const fetchError = ref<string | null>(null);
  const loading = ref(false);

  async function loadFromApi(id: string): Promise<void> {
    if (!id) return;
    loading.value = true;
    fetchError.value = null;
    try {
      const resp = await authFetch(
        apiUrl(`/api/skills/catalog.resource_view?role=${encodeURIComponent(role)}&resource_id=${encodeURIComponent(id)}`),
        { headers: { Accept: 'application/json' } },
      );
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      fetched.value = (await resp.json()) as Record<string, unknown>;
    } catch (e) {
      fetchError.value = e instanceof Error ? e.message : String(e);
      fetched.value = null;
    } finally {
      loading.value = false;
    }
  }

  watch(
    () => resourceId(),
    (id) => {
      fetched.value = null;
      fetchError.value = null;
      // 详情页始终拉 API 富集详情（typedDetail/catalogMeta/分型块 + accessPolicy + 真实 lifecycle）。
      // 0605#2：不再以 snapshot 列表态薄字段先首刷再被 API 覆盖——那会造成「先缩略后详情」的跳跃感。
      if (id) void loadFromApi(id);
    },
    { immediate: true },
  );

  // 只展示 API 返回的完整详情数据，不使用 snapshot 缩略信息（避免首刷跳跃感）。
  const resource = computed(() => fetched.value);

  return { resource, loading, fetchError };
}
