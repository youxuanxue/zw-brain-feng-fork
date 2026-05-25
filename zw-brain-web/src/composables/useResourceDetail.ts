import { computed, ref, watch } from 'vue';
import { authFetch } from './useAuth';
import { lookupResource, useSnapshot } from './useSnapshot';

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
        `/api/skills/catalog.resource_view?role=${encodeURIComponent(role)}&resource_id=${encodeURIComponent(id)}`,
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
      if (!lookupResource(id).value && id) void loadFromApi(id);
    },
    { immediate: true },
  );

  const resource = computed(() => snapshotResource.value ?? fetched.value);

  return { resource, source, loading, fetchError };
}
