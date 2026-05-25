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

function consumeNLAction(action: StructuredAction) {
  if (action.kind === 'filter' && action.payload) {
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
  }
  if (action.kind === 'invoke' && action.target) {
    void invokeActionStub({ skillId: action.target, payload: action.payload, successTitle: action.label });
  } else if (action.kind === 'navigate' && action.target) {
    window.location.hash = action.target;
  }
}

const route = useRoute();
const { query, displayed, searching, searchError, source, isSearchMode } = useDiscoverySearch();

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
    return displayed.value.length ? `命中 ${displayed.value.length} 条可复用资源` : '未命中，可换关键词或浏览专题包';
  }
  return '正在加载资源目录……';
});

async function applyTo(id: string) {
  const result = await invokeActionStub({
    skillId: 'request.create',
    payload: { resource_id: id, purpose: '来自资源发现页发起复用申请' },
    successTitle: '复用申请已起草',
  });
  const requestId = resolveRequestIdFromAction(result);
  if (requestId) navigateToRequestDetail(requestId);
}
</script>

<template>
  <main class="focus-page">
    <section class="panel">
      <PageFocusHeader
        title="可复用资源"
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
        <form role="search" @submit.prevent>
          <label class="sr-only" for="p2-search">搜索资源</label>
          <input
            id="p2-search"
            v-model="query"
            type="search"
            class="focus-search"
            placeholder="例如：停车场信息 / 营商环境 / 一表通"
            autocomplete="off"
          />
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
.card-grid { display: grid; gap: 12px; margin-top: 8px; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }
</style>
