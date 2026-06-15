<script setup lang="ts">
import { computed, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import { invokeActionStub } from '@/composables/useActionStub';
import { navigateToRequestDetail, resolveRequestIdFromAction } from '@/composables/useRequestNavigation';
import { useDiscoverySearch } from '@/composables/useDiscoverySearch';
import ResourceCard from '@/components/ResourceCard.vue';
import NLAcceleratorPanel from '@/components/NLAcceleratorPanel.vue';
import type { StructuredAction } from '@/composables/useNLAccelerator';
import { getProductRole } from '@/composables/useProductRole';
import { canPerformAction } from '@/lib/pageAccess';
import { resourceKindLabel } from '@/lib/resourceKind';

const NL_PRESETS_P2 = ['查省营商环境相关数据', '近 7 天高使用资源', '关联水电气交叉数据'];

// 物化形态 kind → 中文经单源 resourceKindLabel（lib/resourceKind.ts），与 ResourceCard / 资源详情同口径。

function consumeNLAction(action: StructuredAction) {
  if (action.kind === 'filter' && action.payload) {
    // NL 解析出的资源类型 / 提供部门也落入同一筛选状态（与三件套共存不打架）。
    // resourceKindLabel 非空 = 该 kind 为已知 canonical 类型，过滤掉 NL 误解析的杂值。
    if (typeof action.payload.kind === 'string' && resourceKindLabel(action.payload.kind)) {
      filters.kind = action.payload.kind;
    }
    if (typeof action.payload.provider === 'string' && action.payload.provider.trim()) {
      filters.provider = action.payload.provider.trim();
    }
    const next =
      typeof action.payload.query === 'string'
        ? action.payload.query
        : typeof action.payload.zone === 'string'
          ? String(action.payload.zone).replace(/专区$/, '')
          : '';
    if (next.trim()) {
      query.value = next.trim();
      return;
    }
    if (filters.kind || filters.provider) return;
  }
  if (action.kind === 'invoke' && action.target) {
    void invokeActionStub({ skillId: action.target, payload: action.payload, successTitle: action.label });
  } else if (action.kind === 'navigate' && action.target) {
    window.location.hash = action.target;
  }
}

const route = useRoute();
const {
  query,
  filters,
  displayed,
  searching,
  searchError,
  source,
  isSearchMode,
  providerOptions,
  kindOptions,
} = useDiscoverySearch();

onMounted(() => {
  const fromQuery = route.query.q ?? route.query.catalog;
  if (typeof fromQuery === 'string' && fromQuery.trim()) {
    query.value = fromQuery.trim();
  }
});

// G5：申请是申请人动作。request.create = 部门操作员 + 部门管理员（D57④ 管理员申请人身份照 v5
// 保留，与 P2 详情页 canApply、后端 policy.request.create set-equal）；业务运营员 / 审计员在发现页
// 不渲染「申请资源」CTA（无权=不可见，纵深防御叠加 ResourceCard 的 active-only 机器值门）。
const canApply = computed(() => canPerformAction('request.create', getProductRole().value));

// 非申请人岗位（含业务运营员）浏览找数据时不出现「申请资源」字样——页头标题与命中统计同步中性化。
const pageTitle = computed(() => (canApply.value ? '可申请资源' : '数据资源'));

const headerMeta = computed(() => {
  if (searching.value) return '正在检索……';
  if (searchError.value && isSearchMode.value) return `检索失败：${searchError.value}`;
  if (source.value === 'live') {
    if (!displayed.value.length) return '未命中，可换关键词或浏览专题包';
    return canApply.value
      ? `命中 ${displayed.value.length} 条可申请资源`
      : `命中 ${displayed.value.length} 条数据资源`;
  }
  return '正在加载资源目录……';
});

// G5：「我的申请」是申请人入口。业务运营员（受理人，非申请人）不应有此入口——按路由可达性过滤
// （单源 isRouteAllowedForRole）。注意 request-flow 对业务运营员路由可达（受理工作台），故此处用
// 动作语义而非路由可达判定：仅申请人（可 request.create）保留「我的申请」链接。
const headerLinks = computed(() => {
  const links = [
    { label: '目录浏览', href: '#/discovery/catalog-browse' },
    { label: '我的申请', href: '#/request-flow', applicantOnly: true },
  ];
  return links
    .filter((l) => (l.applicantOnly ? canApply.value : true))
    .map(({ label, href }) => ({ label, href }));
});

async function applyTo(id: string) {
  // 采草稿流（0605#8）：生成草稿 → 跳详情确认 → 用户手动提交才进审批。
  // 去掉前端硬塞的零内容用途「通过资源发现页申请资源」（描述 UI 路径≠用户诉求，掩耳盗铃）：
  // 与 P2ResourceDetail.apply 一致只传 resource_id，用途由用户在详情页确认/修订。
  const result = await invokeActionStub({
    skillId: 'request.create',
    payload: { resource_id: id },
    successTitle: '申请草稿已生成，请在详情页确认后提交',
  });
  const requestId = resolveRequestIdFromAction(result);
  if (requestId) navigateToRequestDetail(requestId);
}
</script>

<template>
  <main class="focus-page">
    <section class="panel">
      <PageFocusHeader
        :title="pageTitle"
        :meta="headerMeta"
        :links="headerLinks"
      >
        <template #aside>
          <NLAcceleratorPanel page-anchor="P2" :presets="NL_PRESETS_P2" @action="consumeNLAction" />
        </template>
        <form role="search" class="discovery-filters" @submit.prevent>
          <label class="sr-only" for="p2-search">按名称检索资源</label>
          <input
            id="p2-search"
            v-model="query"
            type="search"
            class="focus-search"
            placeholder="例如：停车场信息 / 营商环境 / 一表通"
            autocomplete="off"
          />
          <!-- 反馈 7：资源类型筛选（库表/文件/文件夹/接口/链接，从结果集现算） -->
          <label class="sr-only" for="p2-kind">按资源类型筛选</label>
          <select id="p2-kind" v-model="filters.kind" class="focus-filter" data-testid="filter-kind">
            <option value="">全部资源类型</option>
            <option v-for="k in kindOptions" :key="k" :value="k">{{ resourceKindLabel(k) || k }}</option>
          </select>
          <!-- 反馈 7：提供部门筛选（真实库 distinct 提供方，不写死） -->
          <label class="sr-only" for="p2-provider">按提供部门筛选</label>
          <select id="p2-provider" v-model="filters.provider" class="focus-filter" data-testid="filter-provider">
            <option value="">全部提供部门</option>
            <option v-for="p in providerOptions" :key="p" :value="p">{{ p }}</option>
          </select>
        </form>
      </PageFocusHeader>

      <div v-if="source === 'live' && displayed.length" class="card-grid">
        <ResourceCard
          v-for="r in displayed"
          :key="String((r as Record<string, unknown>).id ?? '')"
          :resource="(r as Record<string, unknown>)"
          :show-action="canApply"
          @apply="applyTo"
        />
      </div>
      <p v-else-if="source === 'live'" class="focus-empty">未命中资源。</p>
      <p v-else class="focus-empty">等待数据装载……</p>
    </section>
  </main>
</template>

<style scoped>
.card-grid { display: grid; gap: 18px; margin-top: 14px; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }
.discovery-filters { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.discovery-filters .focus-search { flex: 1 1 240px; min-width: 200px; }
.focus-filter { flex: 0 0 auto; padding: 7px 10px; border-radius: 6px; border: 1px solid var(--b-border, #d4e2f4); background: #fff; font-size: 13px; color: var(--b-neutral-text, #1a1d21); cursor: pointer; }
</style>
