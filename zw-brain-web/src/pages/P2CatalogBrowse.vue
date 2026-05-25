<script setup lang="ts">
import { computed } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import { useSnapshot } from '@/composables/useSnapshot';
import { catalogTreeDiscoveryQuery } from '@/lib/discoverySearchFilter';

interface CatalogTreeRow {
  key: string;
  name: string;
  count: number;
  hint: string;
  searchQuery: string | null;
}

const { data, source } = useSnapshot();

const tree = computed((): CatalogTreeRow[] => {
  const discovery = data.value?.discovery as Record<string, unknown> | undefined;
  const nodes = (discovery?.catalogTree as unknown[] | undefined) ?? [];
  return nodes.map((node, index) => {
    const n = node as Record<string, unknown>;
    const name = String(n.name ?? n.label ?? '—');
    const count =
      typeof n.count === 'number'
        ? n.count
        : Array.isArray(n.children)
          ? (n.children as unknown[]).length
          : 0;
    const hint = String(n.hint ?? '');
    const href = n.href;
    const isMasterData =
      Boolean(hint) ||
      href === null ||
      /组织|区划|主数据|projection/i.test(name);
    return {
      key: `${index}-${name}`,
      name,
      count,
      hint,
      searchQuery: isMasterData ? null : catalogTreeDiscoveryQuery(name),
    };
  });
});

const headerMeta = computed(() => {
  if (source.value !== 'live') return '正在加载目录树……';
  if (!tree.value.length) return '暂无目录节点';
  const total = tree.value.reduce((sum, row) => sum + row.count, 0);
  return `${tree.value.length} 个顶级目录 · 合计约 ${total.toLocaleString()} 条`;
});

function discoveryHref(query: string): string {
  return `#/discovery?q=${encodeURIComponent(query)}`;
}
</script>

<template>
  <main class="focus-page">
    <nav class="crumbs"><a href="#/discovery">← 资源发现</a></nav>
    <section class="panel">
      <PageFocusHeader title="目录浏览" :meta="headerMeta" />
      <table v-if="source === 'live' && tree.length" class="focus-table">
        <thead>
          <tr><th>目录名称</th><th>规模</th><th>说明</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in tree" :key="row.key">
            <td>{{ row.name }}</td>
            <td>{{ row.count.toLocaleString() }}</td>
            <td class="hint-cell">{{ row.hint || '—' }}</td>
            <td>
              <a v-if="row.searchQuery" :href="discoveryHref(row.searchQuery)" class="row-link">
                在发现页检索「{{ row.searchQuery }}」
              </a>
              <span v-else class="row-muted">{{ row.hint || '主数据自动同步，不在此检索' }}</span>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else-if="source === 'live'" class="focus-empty">暂无目录数据。</p>
      <p v-else class="focus-empty">等待数据装载……</p>
    </section>
  </main>
</template>

<style scoped>
.row-link { color: var(--b-primary, #006be6); font-size: 13px; text-decoration: none; }
.row-link:hover { text-decoration: underline; }
.row-muted { color: var(--b-muted, #5c6370); font-size: 12px; }
.hint-cell { max-width: 220px; color: var(--b-muted, #5c6370); font-size: 12px; }
</style>
