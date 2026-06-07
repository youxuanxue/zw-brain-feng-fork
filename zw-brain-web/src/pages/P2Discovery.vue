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

const NL_PRESETS_P2 = ['查省营商环境相关数据', '近 7 天高使用资源', '关联水电气交叉数据'];

// 物化形态 kind → 中文（与 ResourceCard 徽标 / 资源详情分型同口径）。
// 资源类型收敛为「库表 / 文件 / API」——文件夹/链接退役。
const KIND_FILTER_LABELS: Record<string, string> = {
  table: '库表',
  file: '文件',
  api: '接口',
};

function consumeNLAction(action: StructuredAction) {
  if (action.kind === 'filter' && action.payload) {
    // NL 解析出的资源类型 / 提供部门也落入同一筛选状态（与三件套共存不打架）。
    if (typeof action.payload.kind === 'string' && KIND_FILTER_LABELS[action.payload.kind]) {
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

const headerMeta = computed(() => {
  if (searching.value) return '正在检索……';
  if (searchError.value && isSearchMode.value) return `检索失败：${searchError.value}`;
  if (source.value === 'live') {
    return displayed.value.length ? `命中 ${displayed.value.length} 条可申请资源` : '未命中，可换关键词或浏览专题包';
  }
  return '正在加载资源目录……';
});

async function applyTo(id: string) {
  const result = await invokeActionStub({
    skillId: 'request.create',
    payload: { resource_id: id, purpose: '通过资源发现页申请资源' },
    successTitle: '资源申请已起草',
  });
  const requestId = resolveRequestIdFromAction(result);
  if (requestId) navigateToRequestDetail(requestId);
}
</script>

<template>
  <main class="focus-page">
    <section class="panel">
      <PageFocusHeader
        title="可申请资源"
        :meta="headerMeta"
        :links="[
          { label: '专题包', href: '#/zones-pack' },
          { label: '目录浏览', href: '#/discovery/catalog-browse' },
          { label: '我的申请', href: '#/request-flow' },
        ]"
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
            <option v-for="k in kindOptions" :key="k" :value="k">{{ KIND_FILTER_LABELS[k] ?? k }}</option>
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
          show-action
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
