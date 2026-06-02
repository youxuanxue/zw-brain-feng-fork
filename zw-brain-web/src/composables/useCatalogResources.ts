import { ref, watch } from 'vue';
import { authFetch } from './useAuth';
import { useSnapshot } from './useSnapshot';
import { apiUrl } from './useApiBase';

/** 目录下资源：调 catalog.resource.list 列出某目录关联的 resource_asset（钻取链路）。 */
export function useCatalogResources(catalogCode: () => string, role = 'ROLE_ORGAN_OPERATER') {
  const catalog = ref<Record<string, unknown> | null>(null);
  const resources = ref<Record<string, unknown>[]>([]);
  const total = ref(0);
  const loading = ref(false);
  const fetchError = ref<string | null>(null);
  const { source } = useSnapshot();

  // resource_asset_to_dict 字段 → ResourceCard 期望键（id/name/status/provider）。
  function mapAssetToCard(a: Record<string, unknown>): Record<string, unknown> {
    return {
      id: String(a.resource_code ?? ''),
      name: String(a.title ?? a.resource_code ?? ''),
      status: String(a.lifecycle_status ?? ''),
      provider: String(a.owner_org_id ?? ''),
      kind: String(a.resource_kind ?? ''),
    };
  }

  async function load(code: string): Promise<void> {
    if (!code) return;
    loading.value = true;
    fetchError.value = null;
    try {
      const resp = await authFetch(apiUrl('/api/skills/catalog.resource.list'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ role, catalog_code: code, limit: 50 }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const body = (await resp.json()) as {
        catalog?: Record<string, unknown>;
        items?: Record<string, unknown>[];
        total?: number;
      };
      catalog.value = body.catalog ?? null;
      resources.value = (body.items ?? []).map(mapAssetToCard);
      total.value = Number(body.total ?? resources.value.length);
    } catch (e) {
      fetchError.value = e instanceof Error ? e.message : String(e);
      catalog.value = null;
      resources.value = [];
      total.value = 0;
    } finally {
      loading.value = false;
    }
  }

  watch(catalogCode, (code) => { void load(code); }, { immediate: true });

  return { catalog, resources, total, loading, fetchError, source };
}
