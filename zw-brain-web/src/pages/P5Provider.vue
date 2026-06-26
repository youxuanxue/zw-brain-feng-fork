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
import { filterByRouteAccess, isRouteAllowedForRole } from '@/lib/pageAccess';
import { canCompileNationalExtElem, canViewProviderAssets } from '@/lib/requestFlowRoles';

const provider = useProvider();
const { source } = useSnapshot();
const role = getProductRole();

const counts = computed(() => providerTodoCounts(provider.value as Record<string, unknown>));

// 目录 / 资源管理概览（负责人加注）：本部门「编了多少 / 在审多少 / 待发布 / 已发布」管理态，
// 让供数人不止看审批待办、还看到自己经手目录与资源的整体情况（真实 snapshot 派生）。
// 入口门 = 清单页视图门同源（canViewProviderAssets，供数三岗位）：操作员=编制者也需看本部门
// 清单跟踪状态（业务方 2026-06-09 确认只读浏览），不得用发布权限门把有权浏览的岗位挡在入口外。
const canViewAssetOverview = computed(() => canViewProviderAssets(role.value));
const catalogSummary = computed(() => providerCatalogSummary(provider.value as Record<string, unknown>));
const resourceSummary = computed(() => providerResourceSummary(provider.value as Record<string, unknown>));

// 协作待办（次区）：审核 / 供需对接 / 异议——计数 + 进**详情收件箱**的导航入口（收件箱办的是
// 工作台不收的多步/长列表流：反向草稿逐字核、异议回复评价、供需撮合）；逐条"点一下就办"的
// 简单是/否（发布/审核/受理）已统一收口到工作台行内办理，本页不再重复承载办理队列。
const collabCards = computed(() => {
  const c = counts.value;
  return [
    // E3（6.4#16）：去工程黑话「字段审核/字段裁决」。该收件箱办理的是「反向编目草稿」的部门审
    // （动作 catalog.entry.reverse_draft.confirm/reject，D57⑧ 第一级=部门管理员；通过后汇入
    // 「目录审核」catalog-review 平台档由业务运营员复核）——按操作实体命名「反向编目审核」，
    // 与「反向编目向导」同词、不与「目录审核」撞名（一词一概念，0608 命名 GATE-2）。
    { key: 'field-decision', label: '反向编目审核', value: c.fieldDec, href: '#/provider/inbox/field-decision' },
    { key: 'hookup-review', label: '挂接审核', value: c.hookup, href: '#/provider/inbox/hookup-review' },
    { key: 'demand-match', label: '供需对接', value: c.demand, href: '#/provider/inbox/demand-match' },
    { key: 'objection', label: '异议响应', value: c.objection, href: '#/provider/inbox/objection' },
  ];
});

// 按当前 role 过滤协作待办卡（单源 = isRouteAllowedForRole，与路由守卫同口径）：
// 挂接审核归部门管理员（G1 照 v5 校正）；反向编目审核（部门审）归部门管理员（D57⑧）；
// 异议响应部门管理员 + 业务运营员（G6）。部门操作员对协作待办全不可见（无权进）。
const visibleStatCards = computed(() =>
  filterByRouteAccess(collabCards.value, (c) => c.href, role.value),
);

// 国家扩展要素编制入口：角色门（MANAGER+BUSIAUDIT）∧ flag 门
// （snapshot.webui.nationalChannel.enabled）。flag-off / 无权 → 入口完全不渲染（无权=不可见）。
const webui = useWebUiConfig();
const nationalChannelEnabled = computed(
  () => ((webui.value.nationalChannel as Record<string, unknown> | undefined)?.enabled === true),
);
const showNationalExtElem = computed(
  () => canCompileNationalExtElem(role.value) && nationalChannelEnabled.value,
);

const headerMeta = computed(() => {
  if (source.value !== 'live') return '正在加载……';
  return '先登记数据源，再编目或挂接；发布与审核在工作台办理';
});

// 供数主线动作提升到页头药丸区（参考找数据页的入口药丸样式）。
// 在线编制目录、反向编目、资源挂接、接口服务注册，按角色权限过滤（无权=不可见）。
const providerHeaderLinks = computed(() => {
  const items = [
    { label: '数据源管理', href: '#/provider/datasources', route: '/provider/datasources' },
    { label: '在线编制目录', href: '#/provider/wizard/inline-catalog', route: '/provider/wizard/inline-catalog' },
    { label: '反向编目', href: '#/provider/wizard/reverse-catalog', route: '/provider/wizard/reverse-catalog' },
    { label: '资源挂接', href: '#/provider/wizard/hookup-submit', route: '/provider/wizard/hookup-submit' },
    { label: '接口服务注册', href: '#/provider/wizard/api-service', route: '/provider/wizard/api-service' },
  ];
  // 无权=不可见：按路由可达性过滤（单源 = isRouteAllowedForRole，与导航/路由守卫同口径），
  // 不另猜 cap 名（未注册 cap 会对全角色放行，反而越权可见）。
  return items.filter((it) => isRouteAllowedForRole(it.route, role.value));
});
</script>

<template>
  <main class="focus-page">
    <section class="panel">
      <PageFocusHeader
        title="提供方管理"
        :meta="headerMeta"
        :links="providerHeaderLinks"
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

      <a
        v-if="showNationalExtElem"
        href="#/provider/national-ext-elem"
        class="nat-ext-entry"
        data-testid="national-ext-elem-entry"
      >
        <strong>国家扩展要素编制</strong>
        <em>与政务目录编制双轨独立，走业务部门→主管部门审核后待国家通道同步</em>
      </a>

      <!-- 协作待办（次区，0605#8）：审核 / 供需对接 / 异议从首屏主视觉降为次级一行；
           进详情收件箱办多步/长列表流。简单发布/审核/受理已收口工作台行内。 -->
      <section v-if="source === 'live' && visibleStatCards.length" class="collab-zone" aria-label="协作待办">
        <h3 class="section-title collab-title">协作待办</h3>
        <div class="stat-grid">
          <a v-for="c in visibleStatCards" :key="c.key" :href="c.href" class="stat-card">
            <strong>{{ c.value }}</strong>
            <em>{{ c.label }}</em>
          </a>
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
.collab-zone { margin-top: 28px; }
.collab-title { margin: 0 0 10px; }
.stat-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 16px; }
.stat-card { display: grid; gap: 4px; padding: 14px 16px; border: 1px solid var(--b-border, #d4e2f4); border-radius: 8px; text-decoration: none; color: inherit; background: #fff; }
.stat-card strong { font-size: 22px; color: var(--b-primary, #006be6); }
.stat-card em { font-style: normal; font-size: 13px; color: var(--b-muted, #5c6370); }
.nat-ext-entry { display: grid; gap: 4px; margin-top: 20px; padding: 14px 16px; border: 1px solid var(--b-border, #d4e2f4); border-radius: 8px; text-decoration: none; color: inherit; background: #f5f9fe; }
.nat-ext-entry strong { font-size: 14px; color: var(--b-primary, #006be6); }
.nat-ext-entry em { font-style: normal; font-size: 12px; color: var(--b-muted, #5c6370); }
.section-title { margin: 0; font-size: 14px; font-weight: 600; }
</style>
