<script setup lang="ts">
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import { lookupDispute, useSnapshot } from '@/composables/useSnapshot';
import { invokeActionStub } from '@/composables/useActionStub';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DetailPanel from '@/components/DetailPanel.vue';
import DetailActions from '@/components/DetailActions.vue';
import { mapDetailRows } from '@/lib/detailDisplay';

const route = useRoute();
const id = computed(() => String(route.params.id ?? ''));
const dispute = lookupDispute(id.value);
const { source } = useSnapshot();

const rows = computed(() => {
  const d = dispute.value;
  if (!d) return mapDetailRows([{ label: '工单编号', value: id.value }]);
  return mapDetailRows([
    { label: '工单编号', value: id.value },
    { label: '标题', value: String(d.title ?? '—') },
    { label: '当前状态', value: String(d.status ?? '—') },
    { label: '相关资源', value: String(d.resource_id ?? d.resource_name ?? '—') },
    { label: '受理时间', value: String(d.opened_at ?? '—') },
  ]);
});

const headerMeta = computed(() => {
  if (dispute.value) return String(dispute.value.title ?? '');
  if (source.value === 'live') return '当前列表中无此工单';
  return '正在加载……';
});

async function escalate() {
  await invokeActionStub({ skillId: 'governance.dispute.escalate', payload: { dispute_id: id.value }, successTitle: '已升级', pendingBackend: 'E4 后台业务 (e4/plan.yaml F3)' });
}
async function resolve() {
  await invokeActionStub({ skillId: 'governance.dispute.resolve', payload: { dispute_id: id.value }, successTitle: '已解决', pendingBackend: 'E4 后台业务' });
}
</script>

<template>
  <main class="focus-page focus-detail">
    <nav class="crumbs"><a href="#/compliance-ops">← 合规与运营</a></nav>
    <section class="panel">
      <PageFocusHeader :title="id" :meta="headerMeta" />
      <DetailPanel title="基本信息" :rows="rows" />
      <DetailActions>
        <button type="button" class="gov-btn gov-btn-secondary" @click="escalate">升级</button>
        <button type="button" class="gov-btn gov-btn-primary" @click="resolve">标记解决</button>
      </DetailActions>
    </section>
  </main>
</template>
