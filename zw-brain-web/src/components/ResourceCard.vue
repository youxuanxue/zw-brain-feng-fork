<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
  resource: Record<string, unknown>;
  showAction?: boolean;
}>();

const item = computed(() => {
  const r = props.resource as Record<string, unknown>;
  return {
    id: String(r.id ?? ''),
    name: String(r.name ?? r.title ?? ''),
    provider: String(r.provider ?? r.providerName ?? ''),
    zone: String(r.zone ?? ''),
    status: String(r.status ?? ''),
    score: r.score,
    desc: String(r.desc ?? r.description ?? ''),
    fields: Array.isArray(r.fields) ? (r.fields as string[]) : [],
    subscribers: r.subscribers,
    coverage: r.coverage,
    kind: String(r.kind ?? ''),
  };
});

// 召回候选（NL 召回字典命中，id="recall:<标题>"）是"提示有这个目录"的软候选：
// 该目录还未录入 catalog_entry 主表（搜不到）、也没有详情页（catalog.resource_view
// 会 entity_not_found）。诚实降级——不渲染会坏的标题链接/查看详情/发起复用申请，
// 只标注"已在官方召回字典、录入中，暂无详情/申请入口"。根因（召回字典↔主表脱节）记 backlog。
const isRecallCandidate = computed(
  () => item.value.kind === 'recall_dictionary' || item.value.id.startsWith('recall:'),
);

const emit = defineEmits<{
  (e: 'apply', id: string): void;
}>();
</script>

<template>
  <article class="res-card">
    <header class="res-head">
      <a v-if="!isRecallCandidate" :href="`#/discovery/resource/${encodeURIComponent(item.id)}`" class="res-title">
        <strong>{{ item.name || item.id }}</strong>
        <span v-if="item.status" class="res-status">{{ item.status }}</span>
      </a>
      <span v-else class="res-title">
        <strong>{{ item.name || item.id }}</strong>
        <span v-if="item.status" class="res-status">{{ item.status }}</span>
      </span>
      <div v-if="item.provider || item.zone" class="res-meta">
        <span v-if="item.provider">{{ item.provider }}</span>
        <span v-if="item.zone"> · {{ item.zone }}</span>
        <span v-if="item.subscribers !== undefined"> · 订阅 {{ item.subscribers }}</span>
        <span v-if="item.coverage"> · 覆盖 {{ item.coverage }}</span>
      </div>
    </header>
    <p v-if="item.desc" class="res-desc">{{ item.desc }}</p>
    <ul v-if="item.fields.length" class="res-fields">
      <li v-for="f in item.fields.slice(0, 8)" :key="f">{{ f }}</li>
    </ul>
    <p v-if="isRecallCandidate" class="res-pending">该目录已在官方召回字典、录入中，暂无详情与申请入口。</p>
    <footer v-if="showAction && !isRecallCandidate" class="res-foot">
      <button type="button" class="gov-btn gov-btn-primary" data-skill="request.create" @click="emit('apply', item.id)">
        发起复用申请
      </button>
      <a :href="`#/discovery/resource/${encodeURIComponent(item.id)}`" class="gov-btn gov-btn-secondary">查看详情</a>
    </footer>
  </article>
</template>

<style scoped>
.res-card { border: 1px solid var(--b-border, #d4e2f4); border-radius: 10px; padding: 16px; background: #fff; display: grid; gap: 8px; }
.res-head { display: grid; gap: 4px; }
.res-title { display: inline-flex; align-items: center; gap: 8px; text-decoration: none; color: inherit; }
.res-title strong { font-size: 16px; }
.res-status { background: var(--b-bg-subtle, #e8f2fc); color: var(--b-primary, #006be6); font-size: 12px; padding: 2px 8px; border-radius: 999px; }
.res-meta { font-size: 12px; color: var(--b-muted, #5c6370); }
.res-pending { font-size: 12px; color: var(--b-muted, #5c6370); margin: 4px 0 0; font-style: italic; }
.res-desc { font-size: 14px; color: var(--b-neutral-text, #1a1d21); margin: 0; line-height: 1.6; }
.res-fields { list-style: none; padding: 0; margin: 0; display: flex; flex-wrap: wrap; gap: 6px; }
.res-fields li { font-size: 12px; background: var(--b-bg-page, #f2f7fd); border: 1px solid var(--b-border, #d4e2f4); border-radius: 999px; padding: 2px 10px; }
.res-foot { display: flex; gap: 8px; margin-top: 8px; }
.gov-btn { display: inline-flex; align-items: center; padding: 6px 14px; border-radius: 6px; font-size: 13px; text-decoration: none; cursor: pointer; border: 1px solid transparent; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
.gov-btn-primary:hover { background: var(--b-primary-hover, #0056c7); }
.gov-btn-secondary { background: #fff; border-color: var(--b-border, #d4e2f4); color: var(--b-neutral-text, #1a1d21); }
.gov-btn-secondary:hover { background: var(--b-bg-subtle, #e8f2fc); }
</style>
