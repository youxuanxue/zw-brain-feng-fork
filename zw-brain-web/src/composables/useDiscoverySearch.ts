import { computed, ref, watch } from 'vue';
import { authFetch } from './useAuth';
import { useDiscoveryResources, useSnapshot } from './useSnapshot';

/** P2 搜索：空 query 用 snapshot 精选 12 条；有关键词时走 data.search 全库检索。 */
export function useDiscoverySearch(role = 'ROLE_ORGAN_OPERATER') {
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
      const resp = await authFetch('/api/skills/data.search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ query: trimmed, page: 1, role }),
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

  watch(query, (q) => {
    if (debounceTimer !== null) window.clearTimeout(debounceTimer);
    debounceTimer = window.setTimeout(() => {
      void runSearch(q);
    }, 350);
  });

  const displayed = computed(() => {
    if (query.value.trim()) return searchResults.value;
    return snapshotResources.value as Record<string, unknown>[];
  });

  const isSearchMode = computed(() => Boolean(query.value.trim()));

  return { query, displayed, searching, searchError, source, isSearchMode };
}
