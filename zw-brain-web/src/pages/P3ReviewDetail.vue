<script setup lang="ts">
import { computed, watchEffect } from 'vue';
import { useRoute } from 'vue-router';
import { lookupRequest, useSnapshot } from '@/composables/useSnapshot';
import { invokeActionStub } from '@/composables/useActionStub';
import { getProductRole } from '@/composables/useProductRole';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DetailPanel from '@/components/DetailPanel.vue';
import DetailActions from '@/components/DetailActions.vue';
import PhaseTrack from '@/components/PhaseTrack.vue';
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

// 三角色脊柱：审批人也看见整单「卡在哪、轮没轮到我」。复用后端已挂在申请卡上的同一条
// status_timeline（#277 单一事实源，含 holder），无需后端——P3ReviewDetail 走 lookupRequest。
const timeline = computed(() => {
  const arr = (req.value as Record<string, unknown> | null)?.statusTimeline;
  return Array.isArray(arr) ? (arr as Array<{ stage: string; status: string; label: string; holder?: string }>) : [];
});

const status = computed(() => String(req.value?.status ?? '').trim().toLowerCase());
const sharedType = computed(() => {
  const raw = (req.value as Record<string, unknown> | null)?.shared_type
    ?? (req.value as Record<string, unknown> | null)?.sharedType;
  return Number(raw ?? 0);
});

// J1 有条件共享 (shared_type=2) 受理/审核两级（受理在前）：
//   第一级 业务运营员受理 (platform_approve)：submitted → dept_approved / rejected
//   第二级 提供方部门管理员审核 (dept_approve)：dept_approved → granted / rejected
// 无条件共享 = 业务运营员受理即终（approval.case.decide，单步 submitted/pending → granted）。
const isConditional = computed(() => sharedType.value === 2);
// 第一级受理（业务运营员）：有条件共享 submitted 单据。
const showAcceptActions = computed(
  () => isPlatformReviewer.value && isConditional.value && status.value === 'submitted',
);
// 第二级部门审核（部门管理员）：有条件共享受理后 dept_approved 单据。
const showDeptReviewActions = computed(
  () => isReviewer.value && status.value === 'dept_approved',
);
// 无条件共享受理即终（业务运营员）：单步通过/退回/驳回。
const showUnconditionalAcceptActions = computed(
  () =>
    isPlatformReviewer.value &&
    !isConditional.value &&
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
    if (showAcceptActions.value) return `${base} · 受理（第一级）`;
    if (showDeptReviewActions.value) return `${base} · 部门审核（第二级）`;
    if (showUnconditionalAcceptActions.value) return `${base} · 受理（无条件即终）`;
    return base;
  }
  if (source.value === 'live') return '未在列表中找到该申请';
  return '正在加载……';
});

// --- 第一级：受理（业务运营员）有条件共享 submitted → dept_approved ---
async function accept() {
  await invokeActionStub({
    skillId: 'application.platform_approve',
    payload: { request_id: id.value, decision: 'approve' },
    successTitle: '已受理（待部门审核）',
  });
}
async function acceptReject() {
  await invokeActionStub({
    skillId: 'application.platform_approve',
    payload: { request_id: id.value, decision: 'reject' },
    successTitle: '受理驳回',
  });
}

// --- 第二级：部门审核（提供方部门管理员）dept_approved → granted ---
async function deptReview() {
  await invokeActionStub({
    skillId: 'application.dept_approve',
    payload: { request_id: id.value, decision: 'approve' },
    successTitle: '审核通过（已授权）',
  });
}
async function deptReviewReject() {
  await invokeActionStub({
    skillId: 'application.dept_approve',
    payload: { request_id: id.value, decision: 'reject' },
    successTitle: '部门审核驳回',
  });
}

// --- 无条件共享：业务运营员受理即终（单步）---
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
      <PhaseTrack :steps="timeline" aria-label="审批进度" />
      <DetailPanel v-if="rows.length" title="审批要点" :rows="rows" />
      <DetailActions v-if="showAcceptActions">
        <button type="button" class="gov-btn gov-btn-primary" @click="accept">受理</button>
        <button type="button" class="gov-btn gov-btn-danger" @click="acceptReject">驳回</button>
      </DetailActions>
      <DetailActions v-else-if="showDeptReviewActions">
        <button type="button" class="gov-btn gov-btn-primary" @click="deptReview">审核通过</button>
        <button type="button" class="gov-btn gov-btn-danger" @click="deptReviewReject">驳回</button>
      </DetailActions>
      <DetailActions v-else-if="showUnconditionalAcceptActions">
        <button type="button" class="gov-btn gov-btn-primary" @click="approve">受理通过</button>
        <button type="button" class="gov-btn gov-btn-secondary" @click="fix">退回补正</button>
        <button type="button" class="gov-btn gov-btn-danger" @click="reject">驳回</button>
      </DetailActions>
    </section>
  </main>
</template>
