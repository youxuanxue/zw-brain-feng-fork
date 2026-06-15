<script setup lang="ts">
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import { lookupDispute, useSnapshot } from '@/composables/useSnapshot';
import { invokeActionStub } from '@/composables/useActionStub';
import { getProductRole } from '@/composables/useProductRole';
import { canPerformAction } from '@/lib/pageAccess';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DetailPanel from '@/components/DetailPanel.vue';
import DetailActions from '@/components/DetailActions.vue';
import { mapDetailRows } from '@/lib/detailDisplay';

const route = useRoute();
const id = computed(() => String(route.params.id ?? ''));
// 权限梳理 0609：安全审计员纯只读——升级/解决写动作仅对有权岗位渲染（无权=不可见，非可见+403）。
const role = getProductRole();
const canEscalate = computed(() => canPerformAction('objection.case.escalate', role.value));
const canResolve = computed(() => canPerformAction('objection.case.close', role.value));
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
  await invokeActionStub({
    skillId: 'objection.case.escalate',
    payload: { objection_id: id.value, opinion: '合规运营升级督办' },
    successTitle: '已升级',
  });
}

async function resolve() {
  await invokeActionStub({
    skillId: 'objection.case.close',
    payload: { objection_id: id.value, opinion: '经核查已解决' },
    successTitle: '已关闭',
  });
}
</script>

<template>
  <main class="focus-page focus-detail">
    <nav class="crumbs"><a href="#/compliance-ops">← 合规与运营</a></nav>
    <section class="panel">
      <PageFocusHeader :title="`工单 ${id}`" :meta="headerMeta" />
      <DetailPanel title="基本信息" :rows="rows" />
      <DetailActions v-if="canEscalate || canResolve">
        <button v-if="canEscalate" type="button" class="gov-btn gov-btn-secondary" @click="escalate">升级</button>
        <button v-if="canResolve" type="button" class="gov-btn gov-btn-primary" @click="resolve">标记解决</button>
      </DetailActions>
    </section>
  </main>
</template>
