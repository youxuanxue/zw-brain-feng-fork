import { computed, ref, watch } from 'vue';
import { authFetch } from './useAuth';
import { lookupResource, useSnapshot } from './useSnapshot';
import { apiUrl } from './useApiBase';

/** 资源详情：优先 snapshot；缺失时 GET catalog.resource_view 拉全库条目。 */
export function useResourceDetail(resourceId: () => string, role = 'ROLE_ORGAN_OPERATER') {
  const fetched = ref<Record<string, unknown> | null>(null);
  const fetchError = ref<string | null>(null);
  const loading = ref(false);
  const snapshotResource = computed(() => lookupResource(resourceId()).value);
  const { source } = useSnapshot();

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
      // 详情页始终拉 API 富集详情（typedDetail/catalogMeta/分型块 + accessPolicy）。
      // snapshot 卡片只承载列表态薄字段（id/name/provider/status），不含分型/编制规范字段；
      // 若仅用 snapshot，详情页会缺反馈 5/6 的分型与编目内容。snapshot 作首屏快照，
      // API 富集后覆盖（DB 非空时替换，对齐 snapshot enrich 既有模式）。
      if (id) void loadFromApi(id);
    },
    { immediate: true },
  );

  // API 富集详情优先（含分型/编制规范）；未到达前用 snapshot 卡片快照首屏。
  const resource = computed(() => fetched.value ?? snapshotResource.value);

  return { resource, source, loading, fetchError };
}
