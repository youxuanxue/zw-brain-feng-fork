<script setup lang="ts">
import { computed, watchEffect } from 'vue';
import { useRoute } from 'vue-router';
import { lookupRequest, useSnapshot } from '@/composables/useSnapshot';
import { invokeActionStub } from '@/composables/useActionStub';
import { getProductRole } from '@/composables/useProductRole';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DetailPanel from '@/components/DetailPanel.vue';
import DetailActions from '@/components/DetailActions.vue';
import { formatTodoStatus } from '@/lib/statusLabels';
import { mapDetailRows } from '@/lib/detailDisplay';
import { canReviewRequests } from '@/lib/requestFlowRoles';

const route = useRoute();
const role = getProductRole();
const id = computed(() => String(route.params.id ?? ''));
const isReviewer = computed(() => canReviewRequests(role.value));

watchEffect(() => {
  if (!id.value || isReviewer.value) return;
  window.location.hash = `#/request-flow/request/${id.value}`;
});
const req = lookupRequest(id.value);
const { source } = useSnapshot();

const rows = computed(() => {
  const r = req.value;
  if (!r) return [];
  return mapDetailRows([
    { label: '申请编号', value: id.value },
    { label: '资源', value: String(r.resourceName ?? '—') },
    { label: '申请人', value: String(r.applicant ?? '—') },
    { label: '用途', value: String(r.purpose ?? '—') },
    { label: '当前状态', value: String(r.status ?? '—') },
  ]);
});

const headerMeta = computed(() => {
  if (req.value) return `状态：${formatTodoStatus(String(req.value.status ?? ''))}`;
  if (source.value === 'live') return '未在列表中找到该申请';
  return '正在加载……';
});

async function approve() {
  await invokeActionStub({
    skillId: 'approval.case.decide',
    payload: { request_id: id.value, decision: 'approve' },
    successTitle: '已通过',
  });
}
async function reject() {
  await invokeActionStub({
    skillId: 'approval.case.decide',
    payload: { request_id: id.value, decision: 'reject' },
    successTitle: '已驳回',
  });
}
async function fix() {
  await invokeActionStub({
    skillId: 'approval.case.decide',
    payload: { request_id: id.value, decision: 'return_for_fix' },
    successTitle: '已退回补正',
  });
}
</script>

<template>
  <main class="focus-page focus-detail">
    <nav class="crumbs"><a href="#/request-flow">← 申请列表</a></nav>
    <section class="panel">
      <PageFocusHeader title="审批详情" :meta="headerMeta" />
      <DetailPanel v-if="rows.length" title="审批要点" :rows="rows" />
      <DetailActions v-if="isReviewer">
        <button type="button" class="gov-btn gov-btn-primary" @click="approve">通过</button>
        <button type="button" class="gov-btn gov-btn-secondary" @click="fix">退回补正</button>
        <button type="button" class="gov-btn gov-btn-danger" @click="reject">驳回</button>
      </DetailActions>
    </section>
  </main>
</template>
