<script setup lang="ts">
import { computed } from 'vue';
import { resourceKindLabel } from '@/lib/resourceKind';
import { displayRecordName, stripKindSuffix } from '@/lib/userLanguage';

const props = defineProps<{
  resource: Record<string, unknown>;
  showAction?: boolean;
}>();

const item = computed(() => {
  const r = props.resource as Record<string, unknown>;
  const kind = String(r.kind ?? r.resource_kind ?? '');
  const accessPolicy =
    r.accessPolicy && typeof r.accessPolicy === 'object'
      ? (r.accessPolicy as Record<string, unknown>)
      : null;
  return {
    id: String(r.id ?? ''),
    name: String(r.name ?? r.title ?? ''),
    provider: String(r.provider ?? r.providerName ?? ''),
    zone: String(r.zone ?? ''),
    // status = 后端已下发的中文展示态（前端零词表，只读不译，R12）；
    // lifecycleStatus = 机器原值，仅供逻辑比对（申请门控 / chip 抑制）。
    status: String(r.status ?? ''),
    lifecycleStatus: String(r.lifecycleStatus ?? ''),
    score: r.score,
    desc: String(r.desc ?? r.description ?? ''),
    fields: Array.isArray(r.fields) ? (r.fields as string[]) : [],
    subscribers: r.subscribers,
    coverage: r.coverage,
    kind,
    // 单源 resourceKindLabel（lib/resourceKind.ts）：service→接口、folder/url/link→file，未知→空。
    kindLabel: resourceKindLabel(kind),
    updatedAt: String(r.updatedAt ?? r.updated_at ?? ''),
    shareType: String(r.shareType ?? accessPolicy?.shareTypeLabel ?? ''),
    shareLevel: String(r.shareLevel ?? accessPolicy?.shareLevel ?? ''),
  };
});

// 召回候选（NL 召回字典命中，id="recall:<标题>"）是"提示有这个目录"的软候选：
// 该目录还未录入 catalog_entry 主表（搜不到）、也没有详情页（catalog.resource_view
// 会 entity_not_found）。诚实降级——不渲染会坏的标题链接/查看详情/发起申请，
// 只标注"已在官方召回字典、录入中，暂无详情/申请入口"。根因（召回字典↔主表脱节）记 backlog。
const isRecallCandidate = computed(
  () => item.value.kind === 'recall_dictionary' || item.value.id.startsWith('recall:'),
);

// R12：卡片标题用真实业务名（displayRecordName 优先真实名，名缺失/为裸 id 时降级为
// 「未命名资源（编码 …末6位）」），再剥工程后缀（_库表资源 等，类型已由徽标承载）——
// 绝不把裸资源 id 当标题直出。
const displayTitle = computed(() =>
  stripKindSuffix(displayRecordName(item.value.name, item.value.id, '资源')),
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
        <strong>{{ displayTitle }}</strong>
        <!-- 反馈4（试用反馈）：默认发现视图本就只展示已发布（D53① active-only），
             「已发布」标签是同义反复——抑制之（比对机器值，不比中文）；非默认态（待发布等）有信息量，保留。 -->
        <span v-if="item.status && item.lifecycleStatus !== 'active'" class="res-status">{{ item.status }}</span>
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
    <footer v-if="!isRecallCandidate" class="res-foot">
      <!-- A1（0605#1）：只有申请人岗位 +「已发布（机器值 active）」资源可申请。
           ResourceCard 仍始终给详情入口；申请 CTA 由父级申请人权限 + active 机器值共同门控。 -->
      <button
        v-if="showAction && item.lifecycleStatus === 'active'"
        type="button"
        class="gov-btn gov-btn-primary"
        data-skill="request.create"
        @click="emit('apply', item.id)"
      >
        发起申请
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
