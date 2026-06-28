<script setup lang="ts">
import { computed, reactive, watchEffect } from 'vue';
import { useRoute } from 'vue-router';
import { lookupRequest, useSnapshot } from '@/composables/useSnapshot';
import { invokeActionStub, pushToast } from '@/composables/useActionStub';
import { getProductRole } from '@/composables/useProductRole';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DetailPanel from '@/components/DetailPanel.vue';
import DetailActions from '@/components/DetailActions.vue';
import PhaseTrack from '@/components/PhaseTrack.vue';
import { formatTodoStatus } from '@/lib/statusLabels';
import { mapDetailRows } from '@/lib/detailDisplay';
import { canReviewRequests, canPlatformReviewRequests } from '@/lib/requestFlowRoles';
import { formatPersonLabel } from '@/lib/userLanguage';

const route = useRoute();
const role = getProductRole();
const id = computed(() => String(route.params.id ?? ''));
const isReviewer = computed(() => canReviewRequests(role.value));
const isPlatformReviewer = computed(() => canPlatformReviewRequests(role.value));

watchEffect(() => {
  if (!id.value || isReviewer.value || isPlatformReviewer.value) return;
  if (id.value.startsWith('resource-review:')) {
    const resourceId = id.value.slice('resource-review:'.length).trim();
    window.location.hash = resourceId
      ? `#/discovery/resource/${encodeURIComponent(resourceId)}`
      : '#/workbench';
    return;
  }
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
const providerOrgCode = computed(() =>
  String(
    (req.value as Record<string, unknown> | null)?.providerOrgCode
      ?? (req.value as Record<string, unknown> | null)?.owner_org_code
      ?? (req.value as Record<string, unknown> | null)?.provider_org_id
      ?? '',
  ).trim(),
);

// J1 有条件共享 (shared_type=2) 受理/审核两级（受理在前）：
//   第一级 业务运营员受理 (platform_approve)：submitted → dept_approved / rejected
//   第二级 提供方部门管理员审核 (dept_approve)：dept_approved → granted / rejected
// 无条件共享 = 业务运营员受理即终（approval.case.decide，单步 submitted/pending → granted）。
const isConditional = computed(() => sharedType.value === 2);
// 历史导入申请 = 只读迁移记录，无运行时受理实体；受理/驳回/部门审核点了后端必拒。
// 「不可动作 = 不可见」——历史导入单整组审批入口不渲染（与 P3RequestDetail 同一 isLegacyImport 守卫）。
// 快照申请卡字段是 isLegacyImport（_record_to_request_card 单一事实源；其余页面均读此名）。
const isLegacyImport = computed(() => Boolean(req.value?.isLegacyImport));
// 国家通道指示（C9）：channel_class==='national' 的申请由业务运营员经工作台转报国家平台
//   （application.escalate_national），不在本页做部门审核/受理。故国家通道单在本页不渲染
//   任何受理/部门审核/驳回按钮（点了后端必拒）。缺省 internal。
const isNationalChannel = computed(
  () =>
    String(
      (req.value as Record<string, unknown> | null)?.channelClass ?? 'internal',
    ) === 'national',
);
// 历史导入单与国家通道单均不在本页办理：审批入口整组不渲染。
const reviewActionable = computed(() => !isLegacyImport.value && !isNationalChannel.value);
// 第一级受理（业务运营员）：有条件共享 submitted 单据。
const showAcceptActions = computed(
  () => reviewActionable.value && isPlatformReviewer.value && isConditional.value && status.value === 'submitted',
);
// 第二级部门审核（部门管理员）：有条件共享受理后 dept_approved 单据。
const showDeptReviewActions = computed(
  () => reviewActionable.value && isReviewer.value && status.value === 'dept_approved',
);
// 无条件共享受理即终（业务运营员）：单步通过/退回/驳回。
const showUnconditionalAcceptActions = computed(
  () =>
    reviewActionable.value &&
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
    { label: '申请人', value: formatPersonLabel(r.applicant ?? '—') },
    { label: '申请部门', value: String(r.applicantDept ?? '—') },
    {
      label: '提供部门',
      value: String(
        r.providerOrgName
          ?? r.provider_org_name
          ?? r.owner_org_name
          ?? r.providerOrgCode
          ?? r.owner_org_code
          ?? '—',
      ),
    },
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

// --- 驳回 / 退回理由门（业务决策：驳回理由必填，空理由不能下发）---
// 范式同 WorkbenchTodoActionPanel：第一次点「驳回 / 退回」只展开行内理由框，填写后「确认」才
// 真正下发；理由经 payload.note 一路透传到后端落库（handler 取 note||reason），并回显给申请人。
// 同一时刻仅一处理由框展开（key = 该决策的下发函数标识）。
type RejectKind = 'accept-reject' | 'dept-reject' | 'reject' | 'fix';
const reasonGate = reactive<{ kind: RejectKind | ''; text: string }>({ kind: '', text: '' });
const reasonLabel = computed(() => (reasonGate.kind === 'fix' ? '退回补正理由' : '驳回理由'));

function openReason(kind: RejectKind): void {
  reasonGate.kind = kind;
  reasonGate.text = '';
}
function cancelReason(): void {
  reasonGate.kind = '';
  reasonGate.text = '';
}
// 必填门：空理由（去空白后为空）不下发——确认按钮 disabled 兜底拦截 + 二次校验提示。
const reasonEmpty = computed(() => !reasonGate.text.trim());

async function dispatchReject(skillId: string, decision: string, successTitle: string): Promise<void> {
  const note = reasonGate.text.trim();
  if (!note) {
    pushToast({ kind: 'warn', title: '请先填写理由', detail: '驳回 / 退回需向申请人说明依据，理由不能为空。' });
    return;
  }
  const payload: Record<string, unknown> = { request_id: id.value, decision, note };
  if (skillId === 'application.dept_approve' && providerOrgCode.value) {
    payload.org_code = providerOrgCode.value;
  }
  const res = await invokeActionStub({
    skillId,
    payload,
    successTitle,
  });
  if (res.ok) cancelReason();
}

// --- 第一级：受理（业务运营员）有条件共享 submitted → dept_approved ---
async function accept() {
  await invokeActionStub({
    skillId: 'application.platform_approve',
    payload: { request_id: id.value, decision: 'approve' },
    successTitle: '已受理（待部门审核）',
  });
}
function confirmAcceptReject() {
  return dispatchReject('application.platform_approve', 'reject', '受理驳回');
}

// --- 第二级：部门审核（提供方部门管理员）dept_approved → granted ---
async function deptReview() {
  const payload: Record<string, unknown> = { request_id: id.value, decision: 'approve' };
  if (providerOrgCode.value) payload.org_code = providerOrgCode.value;
  await invokeActionStub({
    skillId: 'application.dept_approve',
    payload,
    successTitle: '审核通过（已授权）',
  });
}
function confirmDeptReviewReject() {
  return dispatchReject('application.dept_approve', 'reject', '部门审核驳回');
}

// --- 无条件共享：业务运营员受理即终（单步）---
async function approve() {
  await invokeActionStub({
    skillId: 'approval.case.decide',
    payload: { request_id: id.value, decision: 'approve' },
    successTitle: '已通过',
  });
}
function confirmReject() {
  return dispatchReject('approval.case.decide', 'reject', '已驳回');
}
function confirmFix() {
  return dispatchReject('approval.case.decide', 'return_for_fix', '已退回补正');
}
</script>

<template>
  <main class="focus-page focus-detail">
    <nav class="crumbs"><a href="#/workbench">← 工作台</a></nav>
    <section class="panel">
      <PageFocusHeader title="审批详情" :meta="headerMeta" />
      <PhaseTrack :steps="timeline" aria-label="审批进度" />
      <DetailPanel v-if="rows.length" title="审批要点" :rows="rows" />
      <DetailActions v-if="showAcceptActions">
        <button type="button" class="gov-btn gov-btn-primary" @click="accept">受理</button>
        <button type="button" class="gov-btn gov-btn-danger" data-testid="review-reject-btn" @click="openReason('accept-reject')">驳回</button>
      </DetailActions>
      <DetailActions v-else-if="showDeptReviewActions">
        <button type="button" class="gov-btn gov-btn-primary" @click="deptReview">审核通过</button>
        <button type="button" class="gov-btn gov-btn-danger" data-testid="review-reject-btn" @click="openReason('dept-reject')">驳回</button>
      </DetailActions>
      <DetailActions v-else-if="showUnconditionalAcceptActions">
        <button type="button" class="gov-btn gov-btn-primary" @click="approve">受理通过</button>
        <button type="button" class="gov-btn gov-btn-secondary" data-testid="review-fix-btn" @click="openReason('fix')">退回补正</button>
        <button type="button" class="gov-btn gov-btn-danger" data-testid="review-reject-btn" @click="openReason('reject')">驳回</button>
      </DetailActions>

      <!-- 行内必填理由门（驳回 / 退回）：填写后「确认」才真正下发，空理由确认按钮 disabled。 -->
      <div v-if="reasonGate.kind" class="review-reason-box" data-testid="review-reason-box">
        <label for="review-reason">{{ reasonLabel }}（必填，将告知申请人）</label>
        <textarea
          id="review-reason"
          v-model="reasonGate.text"
          rows="3"
          placeholder="请说明依据，便于申请人理解结论或按需调整后重新发起"
          data-testid="review-reason-input"
        />
        <div class="review-reason-actions">
          <button
            v-if="reasonGate.kind === 'accept-reject'"
            type="button"
            class="gov-btn gov-btn-danger"
            :disabled="reasonEmpty"
            data-testid="review-reason-confirm"
            @click="confirmAcceptReject"
          >
            确认驳回
          </button>
          <button
            v-else-if="reasonGate.kind === 'dept-reject'"
            type="button"
            class="gov-btn gov-btn-danger"
            :disabled="reasonEmpty"
            data-testid="review-reason-confirm"
            @click="confirmDeptReviewReject"
          >
            确认驳回
          </button>
          <button
            v-else-if="reasonGate.kind === 'fix'"
            type="button"
            class="gov-btn gov-btn-secondary"
            :disabled="reasonEmpty"
            data-testid="review-reason-confirm"
            @click="confirmFix"
          >
            确认退回
          </button>
          <button
            v-else
            type="button"
            class="gov-btn gov-btn-danger"
            :disabled="reasonEmpty"
            data-testid="review-reason-confirm"
            @click="confirmReject"
          >
            确认驳回
          </button>
          <button type="button" class="gov-btn gov-btn-secondary" @click="cancelReason">取消</button>
        </div>
      </div>
    </section>
  </main>
</template>

<style scoped>
.review-reason-box {
  display: grid;
  gap: 8px;
  max-width: 640px;
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--b-border, #d4e2f4);
}
.review-reason-box label {
  font-size: 13px;
  color: var(--b-muted, #5c6370);
}
.review-reason-box textarea {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid var(--b-border, #d4e2f4);
  border-radius: 6px;
  font-size: 13px;
  font-family: inherit;
}
.review-reason-actions {
  display: flex;
  gap: 10px;
}
.review-reason-actions .gov-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
</style>
