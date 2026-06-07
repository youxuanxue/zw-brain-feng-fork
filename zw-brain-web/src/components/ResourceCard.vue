<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
  resource: Record<string, unknown>;
  showAction?: boolean;
}>();

// resource_kind → 中文物化形态徽标。资源类型收敛为「库表 / 文件 / API」——
// 文件夹/链接已退役（归一化阶段 folder→file、移除 link/url）。service = API 的历史别名，保留。
const KIND_LABELS: Record<string, string> = {
  table: '库表',
  file: '文件',
  api: '接口',
  service: '服务',
};

const item = computed(() => {
  const r = props.resource as Record<string, unknown>;
  const kind = String(r.kind ?? r.resource_kind ?? '');
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
    kind,
    kindLabel: KIND_LABELS[kind] ?? '',
    updatedAt: String(r.updatedAt ?? r.updated_at ?? ''),
    shareType: String(r.shareType ?? ''),
    shareLevel: String(r.shareLevel ?? ''),
  };
});

// 召回候选（NL 召回字典命中，id="recall:<标题>"）是"提示有这个目录"的软候选：
// 该目录还未录入 catalog_entry 主表（搜不到）、也没有详情页（catalog.resource_view
// 会 entity_not_found）。诚实降级——不渲染会坏的标题链接/查看详情/申请资源，
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
      <component
        :is="isRecallCandidate ? 'span' : 'a'"
        v-bind="isRecallCandidate ? {} : { href: `#/discovery/resource/${encodeURIComponent(item.id)}` }"
        class="res-title"
      >
        <span v-if="item.kindLabel" class="res-kind">{{ item.kindLabel }}</span>
        <strong>{{ item.name || item.id }}</strong>
        <!-- 反馈4（试用反馈）：默认发现视图本就只展示可复用（发现页可用性过滤决策），
             「可复用」标签是同义反复——抑制之；非默认态（待发布等）有信息量，保留。 -->
        <span v-if="item.status && item.status !== '可复用'" class="res-status">{{ item.status }}</span>
        <span v-if="item.shareType" class="res-share" :class="`res-share--${item.shareLevel}`">{{ item.shareType }}</span>
      </component>
      <div v-if="item.provider || item.zone || item.updatedAt" class="res-meta">
        <span v-if="item.provider">{{ item.provider }}</span>
        <span v-if="item.zone"> · {{ item.zone }}</span>
        <span v-if="item.subscribers !== undefined"> · 订阅 {{ item.subscribers }}</span>
        <span v-if="item.coverage"> · 覆盖 {{ item.coverage }}</span>
        <span v-if="item.updatedAt"> · 更新 {{ item.updatedAt }}</span>
      </div>
    </header>
    <p v-if="item.desc" class="res-desc">{{ item.desc }}</p>
    <ul v-if="item.fields.length" class="res-fields">
      <li v-for="f in item.fields.slice(0, 8)" :key="f">{{ f }}</li>
    </ul>
    <p v-if="isRecallCandidate" class="res-pending">该目录已收录，正在录入，暂无详情与申请入口。</p>
    <footer v-if="showAction && !isRecallCandidate" class="res-foot">
      <!-- A1（0605#1）：只有「已发布（可复用）」资源可申请。发现页投影已只返已发布态，
           此处再以 status 门控为纵深防御——任何非可复用态（待发布等）不渲染申请按钮。 -->
      <button
        v-if="item.status === '可复用'"
        type="button"
        class="gov-btn gov-btn-primary"
        data-skill="request.create"
        @click="emit('apply', item.id)"
      >
        申请资源
      </button>
      <a :href="`#/discovery/resource/${encodeURIComponent(item.id)}`" class="gov-btn gov-btn-secondary">查看详情</a>
    </footer>
  </article>
</template>

<style scoped>
.res-card { border: 1px solid var(--b-border, #d4e2f4); border-radius: 10px; padding: 14px 16px; background: #fff; display: flex; flex-direction: column; gap: 6px; }
.res-head { display: grid; gap: 4px; }
.res-title { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; text-decoration: none; color: inherit; }
.res-title strong { font-size: 15px; line-height: 1.35; }
.res-kind { background: var(--b-bg-page, #eef4fb); color: var(--b-muted, #5c6370); font-size: 11px; padding: 1px 7px; border-radius: 4px; flex: none; }
.res-status { background: var(--b-bg-subtle, #e8f2fc); color: var(--b-primary, #006be6); font-size: 12px; padding: 2px 8px; border-radius: 999px; flex: none; }
.res-share { font-size: 12px; padding: 2px 8px; border-radius: 999px; flex: none; border: 1px solid transparent; }
.res-share--open { background: #e8f7ee; color: #1a7f47; border-color: #b7e3c8; }
.res-share--conditional { background: #fff4e3; color: #9a6212; border-color: #f3d9a8; }
.res-share--closed { background: #f5e9e9; color: #a3322f; border-color: #e6c3c1; }
.res-meta { font-size: 12px; color: var(--b-muted, #5c6370); }
.res-pending { font-size: 12px; color: var(--b-muted, #5c6370); margin: 4px 0 0; font-style: italic; }
.res-desc { font-size: 14px; color: var(--b-neutral-text, #1a1d21); margin: 0; line-height: 1.6; }
.res-fields { list-style: none; padding: 0; margin: 0; display: flex; flex-wrap: wrap; gap: 6px; }
.res-fields li { font-size: 12px; background: var(--b-bg-page, #f2f7fd); border: 1px solid var(--b-border, #d4e2f4); border-radius: 999px; padding: 2px 10px; }
.res-foot { display: flex; gap: 8px; margin-top: auto; padding-top: 8px; }
.gov-btn { display: inline-flex; align-items: center; padding: 6px 14px; border-radius: 6px; font-size: 13px; text-decoration: none; cursor: pointer; border: 1px solid transparent; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
.gov-btn-primary:hover { background: var(--b-primary-hover, #0056c7); }
.gov-btn-secondary { background: #fff; border-color: var(--b-border, #d4e2f4); color: var(--b-neutral-text, #1a1d21); }
.gov-btn-secondary:hover { background: var(--b-bg-subtle, #e8f2fc); }
</style>
