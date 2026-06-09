<script setup lang="ts">
import { computed, ref } from 'vue';
// ref 用于 showCompilation 折叠态（见下）
import { useRoute } from 'vue-router';
import { useCatalogResources } from '@/composables/useCatalogResources';
import { getProductRole } from '@/composables/useProductRole';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DetailPanel from '@/components/DetailPanel.vue';
import ResourceCard from '@/components/ResourceCard.vue';
import { decisionRows, compilationRows, catalogSummary, DECISION_SECTION_TITLE } from '@/lib/typedDetailDisplay';

const route = useRoute();
const code = computed(() => String(route.params.code ?? ''));
const role = getProductRole();
const { catalog, resources, total, loading, fetchError, source } = useCatalogResources(
  () => code.value,
  role.value,
);

// 物化形式（resource_kind）中文标签 —— 与 ResourceCard 徽标同源。
const KIND_LABELS: Record<string, string> = { table: '库表', file: '文件', api: '接口' };

// 申请人选用哪种物化形式：当一个目录挂了多种形态资源（库表/文件/接口），
// 让申请人按物化形式筛选再申请（闭合 J2 挂数 → J1 用数 端到端最后一格）。
const selectedKind = ref('');
const availableKinds = computed(() => {
  const seen = new Set<string>();
  for (const r of resources.value) {
    const k = String((r as Record<string, unknown>).kind ?? '');
    if (k) seen.add(k);
  }
  return Array.from(seen);
});
const filteredResources = computed(() => {
  if (!selectedKind.value) return resources.value;
  return resources.value.filter((r) => String((r as Record<string, unknown>).kind ?? '') === selectedKind.value);
});

const headerTitle = computed(() => {
  if (catalog.value?.title) return String(catalog.value.title);
  if (loading.value) return '正在加载……';
  return code.value;
});

const headerMeta = computed(() => {
  if (fetchError.value) return `加载失败：${fetchError.value}`;
  if (loading.value || source.value !== 'live') return '正在加载目录资源……';
  return total.value ? `${total.value} 个关联资源` : '该目录暂无关联资源';
});

// 反馈 5 — 目录详情编制规范字段：首屏决策字段（共享/更新/提供方）+ 摘要 + 折叠编目字段全集。
const catalogMeta = computed(() => (catalog.value?.catalogMeta as Record<string, unknown> | undefined) ?? null);
const accessPolicy = computed(() => (catalog.value?.accessPolicy as Record<string, unknown> | undefined) ?? null);
const decisionDetailRows = computed(() => decisionRows(accessPolicy.value, catalogMeta.value));
const compilationDetailRows = computed(() => compilationRows(catalogMeta.value));
const summaryText = computed(() => catalogSummary(catalogMeta.value));
const showCompilation = ref(false);
</script>

<template>
  <main class="focus-page focus-detail">
    <nav class="crumbs"><a href="#/discovery/catalog-browse">← 目录浏览</a></nav>
    <section class="panel">
      <PageFocusHeader :title="headerTitle" :meta="headerMeta" />

      <!-- 反馈 5 首屏：决策字段（共享/更新/提供方）+ 数据资源摘要 -->
      <DetailPanel
        v-if="decisionDetailRows.length"
        :title="DECISION_SECTION_TITLE"
        :rows="decisionDetailRows"
        data-testid="catalog-decision-block"
      />
      <section v-if="summaryText" class="detail-block" data-testid="catalog-summary-block">
        <h2 class="detail-block-title">数据资源摘要</h2>
        <p class="summary-text">{{ summaryText }}</p>
      </section>
      <!-- 反馈 5 折叠：目录编制规范编目字段全集（名称/代码/格式/来源/领域 …） -->
      <section v-if="compilationDetailRows.length" class="detail-block" data-testid="catalog-compilation-block">
        <button
          type="button"
          class="collapse-toggle"
          :aria-expanded="showCompilation"
          data-testid="catalog-compilation-toggle"
          @click="showCompilation = !showCompilation"
        >
          <span>编目信息（目录编制规范字段）</span>
          <span class="collapse-arrow">{{ showCompilation ? '收起' : '展开' }}</span>
        </button>
        <DetailPanel v-if="showCompilation" :rows="compilationDetailRows" />
      </section>

      <!-- 多物化形态时：申请人按物化形式筛选要申请的那一份 -->
      <div v-if="availableKinds.length > 1" class="kind-filter">
        <span class="kind-filter-label">物化形式</span>
        <button type="button" class="kind-chip" :class="{ active: selectedKind === '' }" @click="selectedKind = ''">全部</button>
        <button
          v-for="k in availableKinds"
          :key="k"
          type="button"
          class="kind-chip"
          :class="{ active: selectedKind === k }"
          @click="selectedKind = k"
        >{{ KIND_LABELS[k] ?? k }}</button>
      </div>
      <div v-if="filteredResources.length" class="card-grid">
        <ResourceCard v-for="r in filteredResources" :key="String(r.id ?? '')" :resource="r" />
      </div>
      <p v-else-if="!loading && source === 'live'" class="focus-empty">该目录暂无关联资源。</p>
      <p v-else class="focus-empty">正在加载目录资源……</p>
    </section>
  </main>
</template>

<style scoped>
.card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 12px; margin-top: 8px; }
.focus-empty { font-size: 14px; color: var(--b-muted, #5c6370); margin: 16px 0 0; }
.kind-filter { display: flex; align-items: center; gap: 8px; margin: 12px 0 4px; flex-wrap: wrap; }
.kind-filter-label { font-size: 13px; color: var(--b-muted, #5c6370); }
.kind-chip { padding: 3px 12px; border-radius: 14px; font-size: 12px; cursor: pointer; border: 1px solid var(--b-border, #d4e2f4); background: #fff; color: var(--b-text, #1f2733); }
.kind-chip.active { background: var(--b-primary, #006be6); color: #fff; border-color: var(--b-primary, #006be6); }
.summary-text { margin: 8px 0 0; font-size: 14px; line-height: 1.7; color: var(--b-neutral-text, #1a1d21); }
.collapse-toggle { display: flex; align-items: center; justify-content: space-between; width: 100%; padding: 8px 0; background: none; border: none; cursor: pointer; font-size: 15px; font-weight: 600; color: var(--b-neutral-text, #1a1d21); }
.collapse-arrow { font-size: 13px; font-weight: 400; color: var(--b-primary, #006be6); }
</style>
