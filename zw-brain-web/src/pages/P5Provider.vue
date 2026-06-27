<script setup lang="ts">
import { computed } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import { useProvider, useSnapshot, useWebUiConfig } from '@/composables/useSnapshot';
import { getProductRole } from '@/composables/useProductRole';
import {
  providerTodoCounts,
  providerCatalogSummary,
  providerResourceSummary,
} from '@/lib/providerProjection';
import { filterByRouteAccess } from '@/lib/pageAccess';
import { canCompileNationalExtElem, canViewProviderAssets } from '@/lib/requestFlowRoles';
import { shellNavLabelByKey } from '@/config/productShellNav';

const provider = useProvider();
const { source } = useSnapshot();
const role = getProductRole();
const providerShellTitle = shellNavLabelByKey('provider');

const counts = computed(() => providerTodoCounts(provider.value as Record<string, unknown>));

// 协作待办（次区）：审核 / 供需对接 / 异议——计数 + 进详情收件箱；简单发布/审核/受理已收口工作台行内。
const collabCards = computed(() => {
  const c = counts.value;
  return [
    { key: 'field-decision', label: '反向编目审核', value: c.fieldDec, href: '#/provider/inbox/field-decision' },
    { key: 'hookup-review', label: '挂接审核', value: c.hookup, href: '#/provider/inbox/hookup-review' },
    { key: 'demand-match', label: '供需对接', value: c.demand, href: '#/provider/inbox/demand-match' },
    { key: 'objection', label: '异议响应', value: c.objection, href: '#/provider/inbox/objection' },
  ];
});

const visibleStatCards = computed(() =>
  filterByRouteAccess(collabCards.value, (c) => c.href, role.value),
);

// 目录 / 资源管理概览（负责人加注）：本部门「编了多少 / 在审多少 / 待发布 / 已发布」管理态，
// 让供数人不止看审批待办、还看到自己经手目录与资源的整体情况（真实 snapshot 派生）。
// 入口门 = 清单页视图门同源（canViewProviderAssets，供数三岗位）：操作员=编制者也需看本部门
// 清单跟踪状态（业务方 2026-06-09 确认只读浏览），不得用发布权限门把有权浏览的岗位挡在入口外。
const canViewAssetOverview = computed(() => canViewProviderAssets(role.value));
const catalogSummary = computed(() => providerCatalogSummary(provider.value as Record<string, unknown>));
const resourceSummary = computed(() => providerResourceSummary(provider.value as Record<string, unknown>));

// 国家扩展要素编制入口：角色门（MANAGER+BUSIAUDIT）∧ flag 门
// （snapshot.webui.nationalChannel.enabled）。flag-off / 无权 → 入口完全不渲染（无权=不可见）。
const webui = useWebUiConfig();
const nationalChannelEnabled = computed(
  () => ((webui.value.nationalChannel as Record<string, unknown> | undefined)?.enabled === true),
);
const showNationalExtElem = computed(
  () => canCompileNationalExtElem(role.value) && nationalChannelEnabled.value,
);

const providerEntrySections = computed(() => {
  const sections = [
    {
      key: 'maintain',
      title: '维护数据',
      items: [
        { label: '数据源管理', desc: '登记前置库，供反向编目和资源挂接使用', href: '#/provider/datasources' },
        { label: '在线编制目录', desc: '手工编制并提交本部门目录', href: '#/provider/wizard/inline-catalog' },
        { label: '反向编目', desc: '从已登记数据源选择表并生成目录草稿', href: '#/provider/wizard/reverse-catalog' },
        { label: '资源挂接', desc: '把库表、文件或接口挂到目录下', href: '#/provider/wizard/hookup-submit' },
        { label: '接口服务注册', desc: '登记代理接口服务并提交审核', href: '#/provider/wizard/api-service' },
      ],
    },
    {
      key: 'review',
      title: '审核与响应',
      items: [
        { label: '目录审核', desc: '处理目录部门审或平台审', href: '#/provider/inbox/catalog-review' },
        { label: '反向编目审核', desc: '审核反向编目草稿', href: '#/provider/inbox/field-decision' },
        { label: '挂接审核', desc: '审核资源挂接登记', href: '#/provider/inbox/hookup-review' },
        { label: '供需对接', desc: '响应需求方登记的数据缺口', href: '#/provider/inbox/demand-match' },
        { label: '异议响应', desc: '受理、核查或回复异议', href: '#/provider/inbox/objection' },
        ...(showNationalExtElem.value
          ? [{ label: '国家扩展要素编制', desc: '编制并审核国家通道扩展要素', href: '#/provider/national-ext-elem' }]
          : []),
      ],
    },
  ];
  return sections
    .map((section) => ({
      ...section,
      items: filterByRouteAccess(section.items, (it) => it.href, role.value),
    }))
    .filter((section) => section.items.length > 0);
});

const headerMeta = computed(() => {
  if (source.value !== 'live') return '正在加载……';
  return '先登记数据源，再编目或挂接；发布与审核在工作台办理';
});

</script>

<template>
  <main class="focus-page">
    <section class="panel">
      <PageFocusHeader
        :title="providerShellTitle"
        :meta="headerMeta"
      />

      <!-- 目录 / 资源管理概览（负责人加注）：本部门目录 / 资源的管理态全局感（只读现算）。
           T9：概览卡标题做成可点入口 → 进 provider 子路由清单页（/provider/catalogs、
           /provider/resources），按生命周期浏览本部门全部目录/资源（名称/代码/提供方/生命周期/查看）。
           子路由不进 PRODUCT_SHELL_NAV、不增左导航项（守左导航场景页 ≤10 约束）。
           待发布 / 审核中等计数在此只读呈现；逐条"发布/审核"办理已统一到工作台行内。 -->
      <section v-if="source === 'live' && canViewAssetOverview" class="manage-grid" aria-label="目录与资源管理概览">
        <div class="manage-card" data-testid="catalog-manage-summary">
          <header class="manage-head">
            <a href="#/provider/catalogs" class="manage-title-link" data-testid="catalog-manage-link">目录管理 →</a>
          </header>
          <p class="manage-total">本部门目录 {{ catalogSummary.total }} 项</p>
          <ul class="manage-breakdown">
            <li>草稿 <b>{{ catalogSummary.draft }}</b></li>
            <li>审核中 <b>{{ catalogSummary.reviewing }}</b></li>
            <li>待发布 <b>{{ catalogSummary.pendingPublish }}</b></li>
            <li>已发布 <b>{{ catalogSummary.published }}</b></li>
            <li v-if="catalogSummary.inactive">已停用 <b>{{ catalogSummary.inactive }}</b></li>
          </ul>
        </div>
        <div class="manage-card" data-testid="resource-manage-summary">
          <header class="manage-head">
            <a href="#/provider/resources" class="manage-title-link" data-testid="resource-manage-link">资源管理 →</a>
          </header>
          <p class="manage-total">本部门资源 {{ resourceSummary.total }} 项</p>
          <ul class="manage-breakdown">
            <li>草稿 <b>{{ resourceSummary.draft }}</b></li>
            <li>审核中 <b>{{ resourceSummary.reviewing }}</b></li>
            <li>待发布 <b>{{ resourceSummary.pendingPublish }}</b></li>
            <li>已发布 <b>{{ resourceSummary.published }}</b></li>
            <li v-if="resourceSummary.inactive">已停用 <b>{{ resourceSummary.inactive }}</b></li>
          </ul>
        </div>
      </section>

      <section v-if="source === 'live' && visibleStatCards.length" class="collab-zone" aria-label="协作待办">
        <h3 class="section-title collab-title">协作待办</h3>
        <div class="stat-grid">
          <a v-for="c in visibleStatCards" :key="c.key" :href="c.href" class="stat-card">
            <strong>{{ c.value }}</strong>
            <em>{{ c.label }}</em>
          </a>
        </div>
      </section>

      <section v-if="providerEntrySections.length" class="entry-zone" aria-label="供数据入口">
        <div v-for="section in providerEntrySections" :key="section.key" class="entry-section">
          <h3 class="section-title">{{ section.title }}</h3>
          <div class="entry-grid">
            <a v-for="item in section.items" :key="item.href" :href="item.href" class="entry-link">
              <strong>{{ item.label }}</strong>
              <em>{{ item.desc }}</em>
            </a>
          </div>
        </div>
      </section>

      <p v-if="source !== 'live'" class="focus-empty">等待数据装载……</p>
    </section>
  </main>
</template>

<style scoped>
.manage-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; margin-top: 24px; }
.manage-card { padding: 16px 18px; border: 1px solid var(--b-border, #d4e2f4); border-radius: 8px; background: #fff; }
.manage-head { display: flex; align-items: baseline; margin-bottom: 8px; }
.manage-title-link { font-size: 15px; font-weight: 600; color: var(--b-primary, #006be6); text-decoration: none; }
.manage-title-link:hover { text-decoration: underline; }
.manage-total { margin: 0 0 10px; font-size: 13px; color: var(--b-muted, #5c6370); }
.manage-breakdown { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; }
.manage-breakdown li { font-size: 13px; color: var(--b-neutral-text, #1a1d21); }
.manage-breakdown b { font-weight: 700; color: var(--b-primary, #006be6); margin-left: 4px; }
.entry-zone { display: grid; gap: 18px; margin-top: 24px; }
.entry-section { display: grid; gap: 10px; }
.entry-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px; }
.entry-link { display: grid; gap: 4px; min-height: 76px; padding: 12px 14px; border: 1px solid var(--b-border, #d4e2f4); border-radius: 8px; background: #fff; color: inherit; text-decoration: none; }
.entry-link:hover { border-color: var(--b-primary, #006be6); background: var(--b-bg-subtle, #e8f2fc); text-decoration: none; }
.entry-link strong { font-size: 14px; color: var(--b-primary, #006be6); }
.entry-link em { font-style: normal; font-size: 12px; line-height: 1.45; color: var(--b-muted, #5c6370); }
.section-title { margin: 0; font-size: 14px; font-weight: 600; }
.collab-zone { margin-top: 24px; }
.collab-title { margin-bottom: 10px; }
.stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 10px; }
.stat-card { display: grid; gap: 4px; min-height: 72px; padding: 12px 14px; border: 1px solid var(--b-border, #d4e2f4); border-radius: 8px; background: #fff; color: inherit; text-decoration: none; }
.stat-card strong { font-size: 22px; color: var(--b-primary, #006be6); line-height: 1; }
.stat-card em { font-style: normal; font-size: 12px; color: var(--b-muted, #5c6370); }
</style>
