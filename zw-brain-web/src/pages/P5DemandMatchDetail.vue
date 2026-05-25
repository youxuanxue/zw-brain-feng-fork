<script setup lang="ts">
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DetailPanel from '@/components/DetailPanel.vue';
import DetailActions from '@/components/DetailActions.vue';
import { useProvider, useSnapshot } from '@/composables/useSnapshot';
import { deriveDemandMatches } from '@/lib/providerProjection';
import { invokeActionStub } from '@/composables/useActionStub';
import { mapDetailRows } from '@/lib/detailDisplay';

const route = useRoute();
const id = computed(() => String(route.params.id ?? ''));
const provider = useProvider();
const { source } = useSnapshot();

const item = computed(() =>
  deriveDemandMatches(provider.value as Record<string, unknown>).find((d) => d.id === id.value),
);

const rows = computed(() => {
  const it = item.value;
  if (!it) return [];
  return mapDetailRows([
    { label: '需求编号', value: it.id },
    { label: '需求标题', value: it.title },
    { label: '来源平台', value: it.catalog },
    { label: '当前状态', value: it.status },
  ]);
});

async function matchCatalog() {
  const q = item.value?.title?.slice(0, 24) ?? '停车场';
  await invokeActionStub({
    skillId: 'catalog.entry.query',
    payload: { query: q },
    successTitle: '已检索可匹配目录',
  });
}

async function acceptDemand() {
  await invokeActionStub({
    skillId: 'request.create',
    payload: {
      resource_id: 'res-jbxx-ledger',
      purpose: `对接国家需求 ${id.value}：${item.value?.title ?? ''}`.trim(),
    },
    successTitle: '已起草对接申请',
  });
}
</script>

<template>
  <main class="focus-page focus-detail">
    <nav class="crumbs"><a href="#/provider/inbox/demand-match">← 供需对接</a></nav>
    <section class="panel">
      <PageFocusHeader :title="item?.title ?? `需求 ${id}`" meta="匹配本地目录后起草复用申请" />

      <template v-if="source === 'live' && item">
        <DetailPanel title="需求详情" :rows="rows" />
        <DetailActions>
          <button type="button" class="gov-btn gov-btn-secondary" @click="matchCatalog">检索匹配目录</button>
          <button type="button" class="gov-btn gov-btn-primary" @click="acceptDemand">受理并起草申请</button>
        </DetailActions>
      </template>
      <p v-else-if="source === 'live'" class="focus-empty">未找到该需求编号。</p>
      <p v-else class="focus-empty">等待数据装载……</p>
    </section>
  </main>
</template>

<style scoped>
.gov-btn { padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; border: 1px solid transparent; margin-right: 8px; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
.gov-btn-secondary { background: #fff; border-color: var(--b-border, #d4e2f4); }
</style>
