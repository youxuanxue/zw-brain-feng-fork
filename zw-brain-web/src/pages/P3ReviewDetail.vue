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
import { canReviewRequests, canPlatformReviewRequests } from '@/lib/requestFlowRoles';

const route = useRoute();
const role = getProductRole();
const id = computed(() => String(route.params.id ?? ''));
const isReviewer = computed(() => canReviewRequests(role.value));
const isPlatformReviewer = computed(() => canPlatformReviewRequests(role.value));

watchEffect(() => {
  if (!id.value || isReviewer.value || isPlatformReviewer.value) return;
  window.location.hash = `#/request-flow/request/${id.value}`;
});
const req = lookupRequest(id.value);
const { source } = useSnapshot();

const status = computed(() => String(req.value?.status ?? '').trim().toLowerCase());
const sharedType = computed(() => {
  const raw = (req.value as Record<string, unknown> | null)?.shared_type
    ?? (req.value as Record<string, unknown> | null)?.sharedType;
  return Number(raw ?? 0);
});

// J1 有条件共享 (shared_type=2) 两步审批：
//   第一步 提供方部门管理员 (dept_approve)：submitted → dept_approved / rejected
//   第二步 省大数据局业务运营员 (platform_approve)：dept_approved → granted / rejected
// 无条件共享走既有单步 approval.case.decide（保留兼容）。
const isConditional = computed(() => sharedType.value === 2);
const showDeptActions = computed(
  () => isReviewer.value && isConditional.value && status.value === 'submitted',
);
const showPlatformActions = computed(
  () => isPlatformReviewer.value && status.value === 'dept_approved',
);
const showLegacyActions = computed(
  () =>
    isReviewer.value &&
    !showDeptActions.value &&
    (status.value === 'pending' || status.value === 'submitted'),
);

const rows = computed(() => {
  const r = req.value;
  if (!r) return [];
  return mapDetailRows([
    { label: '申请编号', value: id.value },
    { label: '资源', value: String(r.resourceName ?? '—') },
    { label: '申请人', value: String(r.applicant ?? '—') },
    { label: '用途', value: String(r.purpose ?? '—') },
    { label: '共享方式', value: isConditional.value ? '有条件共享' : '无条件共享' },
    { label: '当前状态', value: formatTodoStatus(String(r.status ?? '—')) },
  ]);
});

const headerMeta = computed(() => {
  if (req.value) {
    const base = `状态：${formatTodoStatus(String(req.value.status ?? ''))}`;
    if (showPlatformActions.value) return `${base} · 平台复核（第二步）`;
    if (showDeptActions.value) return `${base} · 部门审（第一步）`;
    return base;
  }
  if (source.value === 'live') return '未在列表中找到该申请';
  return '正在加载……';
});

// --- 第一步：部门审（提供方部门管理员）---
async function deptApprove() {
  await invokeActionStub({
    skillId: 'application.dept_approve',
    payload: { request_id: id.value, decision: 'approve' },
    successTitle: '部门已同意（待平台复核）',
  });
}
async function deptReject() {
  await invokeActionStub({
    skillId: 'application.dept_approve',
    payload: { request_id: id.value, decision: 'reject' },
    successTitle: '已驳回',
  });
}

// --- 第二步：平台复核（省大数据局业务运营员）---
async function platformApprove() {
  await invokeActionStub({
    skillId: 'application.platform_approve',
    payload: { request_id: id.value, decision: 'approve' },
    successTitle: '已授权',
  });
}
async function platformReject() {
  await invokeActionStub({
    skillId: 'application.platform_approve',
    payload: { request_id: id.value, decision: 'reject' },
    successTitle: '平台复核驳回',
  });
}

// --- 无条件共享：既有单步审批（保留兼容）---
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
      <DetailActions v-if="showDeptActions">
        <button type="button" class="gov-btn gov-btn-primary" @click="deptApprove">部门同意</button>
        <button type="button" class="gov-btn gov-btn-danger" @click="deptReject">驳回</button>
      </DetailActions>
      <DetailActions v-else-if="showPlatformActions">
        <button type="button" class="gov-btn gov-btn-primary" @click="platformApprove">通过</button>
        <button type="button" class="gov-btn gov-btn-danger" @click="platformReject">驳回</button>
      </DetailActions>
      <DetailActions v-else-if="showLegacyActions">
        <button type="button" class="gov-btn gov-btn-primary" @click="approve">通过</button>
        <button type="button" class="gov-btn gov-btn-secondary" @click="fix">退回补正</button>
        <button type="button" class="gov-btn gov-btn-danger" @click="reject">驳回</button>
      </DetailActions>
    </section>
  </main>
</template>
