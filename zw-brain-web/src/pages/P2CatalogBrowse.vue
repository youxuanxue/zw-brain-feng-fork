<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import { useSnapshot } from '@/composables/useSnapshot';
import { authFetch } from '@/composables/useAuth';
import { getProductRole } from '@/composables/useProductRole';
import { apiUrl } from '@/composables/useApiBase';
import { displayRecordName, isTestMarkerName } from '@/lib/userLanguage';

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
      errorMsg.value = '暂时无法加载目录，请稍后再试。';
      return;
    }
    const body = (await resp.json()) as { items?: Array<Record<string, unknown>>; total?: number };
    const rawItems = (body.items ?? []).filter((it) => String(it.catalog_code ?? ''));
    // (b) 先剔除明显的测试/样例/乱码目录行（按原始标题判定），被过滤条数经 console.debug 记录。
    const kept = rawItems.filter((it) => !isTestMarkerName(String(it.title ?? '')));
    const filtered = rawItems.length - kept.length;
    if (filtered > 0) {
      console.debug(`[P2CatalogBrowse] 过滤 ${filtered} 条测试/样例目录（共 ${rawItems.length} 条）`);
    }
    rows.value = kept.map((it) => {
      const catalogCode = String(it.catalog_code ?? '');
      const rawTitle = String(it.title ?? '');
      const rawDesc = String(it.description ?? '').trim();
      // (c) 说明 == 名称 / 是测试样例 → 留空（模板渲染「—」），不重复堆名或冒出脏样例。
      const description =
        !rawDesc || rawDesc === rawTitle || isTestMarkerName(rawDesc) ? '' : rawDesc;
      return {
        catalogCode,
        // (a) 名缺失 / 名==编码 / 名是裸 id 编码 → 派生「未命名目录（编码 …末6位）」，不裸出目录编码。
        title: displayRecordName(rawTitle, catalogCode, '目录'),
        resourceCount: Number(it.resourceCount ?? 0),
        // owner 名缺失时回落部门 id 也不直出，统一显示「—」。
        owner: String(it.ownerName ?? '') || '—',
        description,
      };
    }).sort((a, b) => {
      const resourceRank = Number(b.resourceCount > 0) - Number(a.resourceCount > 0);
      if (resourceRank !== 0) return resourceRank;
      return a.title.localeCompare(b.title, 'zh-Hans-CN');
    });
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
      <div v-else-if="source === 'live'" class="focus-empty catalog-empty">
        <p>暂无目录数据。</p>
        <div class="empty-actions" aria-label="暂无目录后的下一步">
          <a class="row-link" href="#/discovery">返回找数据</a>
          <a class="row-link" href="#/request-flow/supply-demand">登记需求 / 找不到数据</a>
        </div>
      </div>
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
.catalog-empty { display: flex; flex-direction: column; gap: 8px; }
.catalog-empty p { margin: 0; }
.empty-actions { display: flex; flex-wrap: wrap; gap: 12px; }
</style>
