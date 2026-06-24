import { computed, reactive, ref, watch, type Ref } from 'vue';
import { authFetch } from './useAuth';
import { useDiscoveryResources, useSnapshot } from './useSnapshot';
import {
  mergeDiscoveryResults,
  applyDiscoveryFilters,
  distinctProviders,
  presentKinds,
  type DiscoveryFilters,
} from '@/lib/discoverySearchFilter';
import { apiUrl } from './useApiBase';

type RoleSource = string | Ref<string> | (() => string);
const DEFAULT_ROLE = 'ROLE_ORGAN_OPERATER';

function resolveRole(role: RoleSource): string {
  if (typeof role === 'function') return role() || DEFAULT_ROLE;
  if (typeof role === 'object' && role !== null && 'value' in role) return String(role.value || DEFAULT_ROLE);
  return String(role || DEFAULT_ROLE);
}

/** P2 搜索：空 query 用 snapshot 精选；有关键词时本地即时筛选 + data.search 全库检索。 */
export function useDiscoverySearch(role: RoleSource = DEFAULT_ROLE) {
  const query = ref('');
  const searchResults = ref<Record<string, unknown>[]>([]);
  const searching = ref(false);
  const searchError = ref<string | null>(null);
  const snapshotResources = useDiscoveryResources();
  const { source } = useSnapshot();

  let debounceTimer: number | null = null;

  async function runSearch(q: string): Promise<void> {
    const trimmed = q.trim();
    if (!trimmed) {
      searchResults.value = [];
      searchError.value = null;
      return;
    }
    searching.value = true;
    searchError.value = null;
    try {
      const resp = await authFetch(apiUrl('/api/skills/data.search'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ query: trimmed, page: 1, role: resolveRole(role) }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = (await resp.json()) as { results?: unknown[] };
      searchResults.value = (data.results ?? []) as Record<string, unknown>[];
    } catch (e) {
      searchError.value = e instanceof Error ? e.message : String(e);
      searchResults.value = [];
    } finally {
      searching.value = false;
    }
  }

  watch([query, () => resolveRole(role)], ([q]) => {
    if (debounceTimer !== null) window.clearTimeout(debounceTimer);
    if (!q.trim()) {
      searchResults.value = [];
      searchError.value = null;
      searching.value = false;
      return;
    }
    debounceTimer = window.setTimeout(() => {
      void runSearch(q);
    }, 350);
  });

  // 反馈 7 — 资源类型 + 提供部门筛选状态。NL 加速器解析结果也写入此 filters，三件套共存。
  const filters = reactive<DiscoveryFilters>({ kind: '', provider: '' });

  // 名称检索 merge 后的全集（未按类型/部门收窄）——用于现算筛选选项，避免「筛完没选项」。
  const nameMatched = computed(() => {
    const snapshot = snapshotResources.value as Record<string, unknown>[];
    return mergeDiscoveryResults(snapshot, searchResults.value, query.value);
  });

  const displayed = computed(() => applyDiscoveryFilters(nameMatched.value, filters));

  // 提供部门下拉从当前名称命中集现算（真实库 distinct，不写死）。
  const providerOptions = computed(() => distinctProviders(nameMatched.value));
  // 资源类型筛选项 = 结果集里真实出现的类型（库表/文件/文件夹/接口/链接）。
  const kindOptions = computed(() => presentKinds(nameMatched.value));

  const isSearchMode = computed(
    () => Boolean(query.value.trim()) || Boolean(filters.kind) || Boolean(filters.provider),
  );

  return {
    query,
    filters,
    displayed,
    searching,
    searchError,
    source,
    isSearchMode,
    providerOptions,
    kindOptions,
  };
}
