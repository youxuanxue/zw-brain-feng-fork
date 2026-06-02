<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import { useSnapshot } from '@/composables/useSnapshot';
import { authFetch } from '@/composables/useAuth';
import { getProductRole } from '@/composables/useProductRole';
import { apiUrl } from '@/composables/useApiBase';

// 目录浏览：真接 catalog.browse 列真 catalog_entry，每行可钻取到目录详情（看目录下资源）。
const { source } = useSnapshot();
const role = getProductRole();

interface CatalogRow {
  catalogCode: string;
  title: string;
  resourceCount: number;
  owner: string;
  description: string;
}

const rows = ref<CatalogRow[]>([]);
const total = ref(0);
const loading = ref(false);
const errorMsg = ref('');

async function load(): Promise<void> {
  loading.value = true;
  errorMsg.value = '';
  try {
    const resp = await authFetch(apiUrl('/api/skills/catalog.browse'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ role: role.value, lifecycle: 'active', limit: 100 }),
    });
    if (!resp.ok) {
      rows.value = [];
      errorMsg.value = `加载失败：HTTP ${resp.status}`;
      return;
    }
    const body = (await resp.json()) as { items?: Array<Record<string, unknown>>; total?: number };
    rows.value = (body.items ?? [])
      .map((it) => ({
        catalogCode: String(it.catalog_code ?? ''),
        title: String(it.title ?? it.catalog_code ?? ''),
        resourceCount: Number(it.resourceCount ?? 0),
        owner: String(it.ownerName ?? it.owner_org_id ?? '—'),
        description: String(it.description ?? ''),
      }))
      .filter((it) => it.catalogCode);
    total.value = Number(body.total ?? rows.value.length);
  } finally {
    loading.value = false;
  }
}

const headerMeta = computed(() => {
  if (source.value !== 'live') return '正在加载目录……';
  if (errorMsg.value) return errorMsg.value;
  return rows.value.length ? `${total.value} 个目录` : '暂无目录';
});

watch(source, (live) => { if (live === 'live') void load(); }, { immediate: true });
watch(role, () => { void load(); });
</script>

<template>
  <main class="focus-page">
    <nav class="crumbs"><a href="#/discovery">← 资源发现</a></nav>
    <section class="panel">
      <PageFocusHeader title="目录浏览" :meta="headerMeta" />
      <table v-if="source === 'live' && rows.length" class="focus-table">
        <thead>
          <tr><th>目录名称</th><th>资源数</th><th>责任方</th><th>说明</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.catalogCode">
            <td>{{ row.title }}</td>
            <td><span class="res-count" :class="{ 'res-count-zero': row.resourceCount === 0 }">{{ row.resourceCount }}</span></td>
            <td>{{ row.owner }}</td>
            <td class="hint-cell">{{ row.description || '—' }}</td>
            <td>
              <a :href="`#/discovery/catalog/${encodeURIComponent(row.catalogCode)}`" class="row-link">查看目录资源</a>
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
.hint-cell { max-width: 280px; color: var(--b-muted, #5c6370); font-size: 12px; }
.res-count { font-weight: 600; color: var(--b-primary, #006be6); }
.res-count-zero { color: var(--b-muted, #5c6370); font-weight: 400; }
</style>
