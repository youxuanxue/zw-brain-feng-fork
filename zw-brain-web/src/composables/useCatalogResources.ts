import { ref, watch, type Ref } from 'vue';
import { authFetch } from './useAuth';
import { useSnapshot } from './useSnapshot';
import { apiUrl } from './useApiBase';

type RoleSource = string | Ref<string> | (() => string);
const DEFAULT_ROLE = 'ROLE_ORGAN_OPERATER';

function resolveRole(role: RoleSource): string {
  if (typeof role === 'function') return role() || DEFAULT_ROLE;
  if (typeof role === 'object' && role !== null && 'value' in role) return String(role.value || DEFAULT_ROLE);
  return String(role || DEFAULT_ROLE);
}

/** 目录下资源：调 catalog.resource.list 列出某目录关联的 resource_asset（钻取链路）。 */
export function useCatalogResources(catalogCode: () => string, role: RoleSource = DEFAULT_ROLE) {
  const catalog = ref<Record<string, unknown> | null>(null);
  const resources = ref<Record<string, unknown>[]>([]);
  const total = ref(0);
  const loading = ref(false);
  const fetchError = ref<string | null>(null);
  const { source } = useSnapshot();

  // resource_asset_to_dict 字段 → ResourceCard 期望键（id/name/status/provider）。
  // status = 后端中文展示态 lifecycle_label（前端零词表）；lifecycleStatus = 机器原值供逻辑比对。
  function mapAssetToCard(a: Record<string, unknown>): Record<string, unknown> {
    const accessPolicy =
      a.accessPolicy && typeof a.accessPolicy === 'object'
        ? (a.accessPolicy as Record<string, unknown>)
        : null;
    return {
      id: String(a.resource_code ?? ''),
      name: String(a.title ?? a.resource_code ?? ''),
      status: String(a.lifecycle_label ?? ''),
      lifecycleStatus: String(a.lifecycle_status ?? ''),
      provider: String(a.owner_org_id ?? ''),
      kind: String(a.resource_kind ?? ''),
      accessPolicy,
      shareType: String(a.shareType ?? accessPolicy?.shareTypeLabel ?? ''),
      shareLevel: String(a.shareLevel ?? accessPolicy?.shareLevel ?? ''),
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
        body: JSON.stringify({ role: resolveRole(role), catalog_code: code, limit: 50, lifecycle: 'active' }),
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

  watch([catalogCode, () => resolveRole(role)], ([code]) => { void load(code); }, { immediate: true });

  return { catalog, resources, total, loading, fetchError, source };
}
