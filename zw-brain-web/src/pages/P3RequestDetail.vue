<script setup lang="ts">
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import { lookupRequest, useSnapshot } from '@/composables/useSnapshot';
import { invokeActionStub, pushToast } from '@/composables/useActionStub';
import { getProductRole } from '@/composables/useProductRole';
import { canPerformAction, hasRole } from '@/lib/pageAccess';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DetailPanel from '@/components/DetailPanel.vue';
import DetailActions from '@/components/DetailActions.vue';
import EditableFormPanel from '@/components/EditableFormPanel.vue';
import PhaseTrack from '@/components/PhaseTrack.vue';
import { mapDetailRows } from '@/lib/detailDisplay';
import type { FormField } from '@/lib/formFields';
import { formatTodoStatus } from '@/lib/statusLabels';

const route = useRoute();
const id = computed(() => String(route.params.id ?? ''));
const req = lookupRequest(id.value);
const { source } = useSnapshot();

const rows = computed(() => {
  const r = req.value;
  if (!r) return [];
  const raw: { label: string; value: string; state?: string; source?: string }[] = [];
  if (r.resourceName) raw.push({ label: '申请资源', value: String(r.resourceName) });
  if (r.applicant) raw.push({ label: '申请人', value: String(r.applicant) });
  if (r.applicantDept) raw.push({ label: '申请部门', value: String(r.applicantDept) });
  if (r.purpose) raw.push({ label: '使用用途', value: String(r.purpose) });
  if (r.range) raw.push({ label: '覆盖范围', value: String(r.range) });
  // 「当前状态」扁平行仅在无进度 stepper 时保留（历史导入单等）；有 stepper 时旅程已述状态，删冗余。
  const hasTimeline = Array.isArray(r.statusTimeline) && r.statusTimeline.length > 0;
  if (r.status && !hasTimeline) raw.push({ label: '当前状态', value: String(r.status) });
  if (r.submittedAt) raw.push({ label: '提交时间', value: String(r.submittedAt) });
  return mapDetailRows(raw);
});

const prefilled = computed(() => {
  const arr = req.value?.prefilledFields;
  if (!Array.isArray(arr)) return [];
  return mapDetailRows(
    (arr as Record<string, unknown>[]).map((it) => ({
      label: String(it.label ?? ''),
      value: String(it.value ?? ''),
      state: it.state ? String(it.state) : undefined,
      source: it.source ? String(it.source) : undefined,
    }))
  );
});

// 表单填报（form-autofill）：草稿/待补正态可原地编辑的字段（含确定性带出 + AI建议 + 锁定）。
const formFields = computed<FormField[]>(() => {
  const arr = req.value?.formFields;
  return Array.isArray(arr) ? (arr as unknown as FormField[]) : [];
});

const headerMeta = computed(() => {
  if (req.value) {
    const status = formatTodoStatus(String(req.value.status ?? ''));
    const name = String(req.value.resourceName ?? req.value.purpose ?? '') || '—';
    return `${name} · ${status}`;
  }
  if (source.value !== 'live') return '正在加载……';
  return '未找到该申请';
});

const rawStatus = computed(() => String(req.value?.status ?? '').trim());

// 申请进度（申请人视角）：后端 status_timeline 是单一事实源，快照申请卡已带 statusTimeline；
// 前端只渲染、不在此重新派生 4 段逻辑（避免第二事实源）。未提交草稿 → 后端返空 → 不渲染。
interface TimelineStep { stage: string; status: string; label: string; holder?: string }
const timeline = computed<TimelineStep[]>(() => {
  const arr = req.value?.statusTimeline;
  return Array.isArray(arr) ? (arr as unknown as TimelineStep[]) : [];
});
// request.submit = OPERATER + MANAGER（D57④）；BUSIAUDIT（受理岗）进申请详情时不渲染「确认提交 / 重新提交」
const canSubmitRequest = computed(() => canPerformAction('request.submit', getProductRole().value));
// 草稿态（0605#8）：从 P2「申请资源」生成的草稿单，用户在此查看无误后「确认提交申请」才进审批。
const isDraft = computed(() => rawStatus.value === 'draft');
// 两条「申请人重提」腿（j1-approval-conditional.feature:55-62）：
//   need-fix（退回补正）→ request.submit；
//   rejected（受理/审核驳回，legacy 3 驳回）→ application.dept_approve {decision:'resubmit'}
//     （conditional_approval.applicant_resubmit：rejected → submitted, round+1）。
// 两态都让申请人原地编辑字段后重提，故 canResubmit 同时覆盖。
const isRejected = computed(() => rawStatus.value === 'rejected');
const canResubmit = computed(() => isRejected.value || rawStatus.value === 'need-fix');

// 撤回 / 暂停授权：write-critical。j1-credential-revoke 决策 A（已签字）——
// 撤回 = 业务运营员合规收回（收回授权）+ 申请人本人主动放弃（我不再需要,owner 校验在后端）；
// 暂停 = 业务运营员。MANAGER 已收回该权限,「无权 = 不可见」整段不渲染。
// 仅对已授权（granted）/ 交付中 / 暂停（suspended）的申请显示,避免对草稿/审批中误操作。
const productRole = computed(() => getProductRole().value);
// R-014：身份分支走 hasRole chokepoint（区分同一 grant 动作的合规收回 vs 申请人放弃
// 两个按钮变体），不在 page 内硬编码 role 比对；「能不能」仍由 canPerformAction 判。
const isBusiAudit = computed(() => hasRole(productRole.value, 'ROLE_BUSIAUDIT'));
const isApplicant = computed(() => hasRole(productRole.value, 'ROLE_ORGAN_OPERATER'));
const canRevokeGrant = computed(() => canPerformAction('application.grant.revoke', productRole.value));
const canSuspendGrant = computed(() => canPerformAction('application.grant.suspend', productRole.value));
// debt j1-legacy-record-actionability：历史导入申请 = 只读迁移记录，无运行时交付实体，
// 撤回/暂停是运行时专属动作（后端只读卡无 delivery 不可 mutate）。「不可动作 = 不可见」——
// 历史导入单整组动作入口不渲染（非可见+失败），避免点了报错的半截功能。
// 快照申请卡字段是 isLegacyImport（_record_to_request_card 单一事实源；其余页面均读此名）。
// 历史回归：此前误读 legacyImport（永远 undefined）→ 历史导入单的只读 banner 不显、运行时
// 动作按钮反而渲染（点了 422 的半截功能，违背下方 88-90 注释意图）。校正为 isLegacyImport。
const isLegacyImport = computed(() => Boolean(req.value?.isLegacyImport));
const grantActive = computed(
  () => !isLegacyImport.value && ['granted', 'in_delivery', 'suspended'].includes(rawStatus.value),
);
const alreadySuspended = computed(() => rawStatus.value === 'suspended');

// 业务运营员合规收回：destructive,成功后给 warn 级红色提示（申请人侧工作台亦显示已撤销红态）。
async function revokeGrant() {
  if (
    !window.confirm(
      `确认收回申请 ${id.value} 的授权？此操作不可逆，申请人需重新提交申请，且会写审计。`,
    )
  ) {
    return;
  }
  const res = await invokeActionStub({
    skillId: 'application.grant.revoke',
    payload: { request_id: id.value },
    successTitle: '已收回授权',
  });
  if (res.ok) {
    pushToast({ kind: 'warn', title: '授权已收回', detail: '申请人需重新提交申请方可继续使用。' });
  }
}

// 申请人本人主动放弃：自己发起,不做「通知」态,给中性确认；后端按 OPERATER 角色判 initiated_by=applicant。
async function abandonGrant() {
  if (
    !window.confirm(
      `确认放弃申请 ${id.value} 的授权？放弃后不可恢复，如需再次使用须重新提交申请。`,
    )
  ) {
    return;
  }
  const res = await invokeActionStub({
    skillId: 'application.grant.revoke',
    payload: { request_id: id.value },
    successTitle: '已放弃授权',
  });
  if (res.ok) {
    pushToast({ kind: 'info', title: '已放弃授权', detail: '如需再次使用该数据，请重新提交申请。' });
  }
}

async function suspendGrant() {
  if (
    !window.confirm(
      `确认暂停申请 ${id.value} 的授权？暂停期间申请人无法访问数据，授权不失效、可恢复，会写审计。`,
    )
  ) {
    return;
  }
  const res = await invokeActionStub({
    skillId: 'application.grant.suspend',
    payload: { request_id: id.value },
    successTitle: '已暂停授权',
  });
  if (res.ok) {
    pushToast({ kind: 'warn', title: '授权已暂停', detail: '申请人暂时无法访问数据，可随时恢复。' });
  }
}

// 草稿确认提交（0605#8）：draft → pending，此刻才启动审批工作流（后端 request.submit 接 draft）。
async function submitDraft() {
  if (!isDraft.value) return;
  const res = await invokeActionStub({
    skillId: 'request.submit',
    payload: { request_id: id.value },
    successTitle: '申请已提交，进入审批',
  });
  if (res.ok) {
    pushToast({ kind: 'info', title: '已提交申请', detail: '申请已进入受控准入，可在「我的申请」跟踪审批进度。' });
  }
}

async function supplement() {
  if (!canResubmit.value) {
    pushToast({
      kind: 'info',
      title: '暂不可重新提交',
      detail:
        rawStatus.value === 'pending'
          ? '申请仍在审批中；若需补件请等待审批人「退回补正」后再点重新提交。'
          : '当前状态不支持重新提交。',
    });
    return;
  }
  // rejected（受理/审核驳回）→ application.dept_approve {decision:'resubmit'}
  //   （conditional_approval.applicant_resubmit：rejected → submitted, round+1）。
  // need-fix（退回补正）→ request.submit（既有补件腿不变）。
  if (isRejected.value) {
    await invokeActionStub({
      skillId: 'application.dept_approve',
      payload: { request_id: id.value, decision: 'resubmit' },
      successTitle: '已重新提交',
    });
    return;
  }
  await invokeActionStub({
    skillId: 'request.submit',
    payload: { request_id: id.value },
    successTitle: '已重新提交',
  });
}
</script>

<template>
  <main class="focus-page focus-detail">
    <nav class="crumbs"><a href="#/delivery-exchange">← 我的申请</a></nav>
    <section class="panel">
      <PageFocusHeader :title="id" :meta="headerMeta" />
      <p v-if="isLegacyImport" class="legacy-note">
        历史导入记录 · 仅供查看，在线办理动作不适用于历史迁移申请。
      </p>
      <PhaseTrack :steps="timeline" aria-label="申请进度" />
      <DetailPanel v-if="rows.length" title="基本信息" :rows="rows" />
      <EditableFormPanel
        v-if="(isDraft || canResubmit) && formFields.length"
        :request-id="id"
        :model-fields="formFields"
      />
      <DetailPanel v-if="prefilled.length" title="系统预填字段" :rows="prefilled" />
      <p class="aux-links">
        <a href="#/request-flow/objection">我的异议</a>
        ·
        <a href="#/request-flow/supply-demand">找不到数据 · 登记需求</a>
      </p>
      <DetailActions
        v-if="!isLegacyImport && (canSubmitRequest || (canSuspendGrant && grantActive) || (canRevokeGrant && grantActive))"
      >
        <button
          v-if="canSubmitRequest && isDraft"
          type="button"
          class="gov-btn gov-btn-primary"
          data-testid="submit-draft-btn"
          @click="submitDraft"
        >
          确认提交申请
        </button>
        <button
          v-if="canSubmitRequest && !isDraft"
          type="button"
          class="gov-btn gov-btn-primary"
          data-testid="resubmit-btn"
          @click="supplement"
        >
          补件 / 重新提交
        </button>
        <button
          v-if="canSuspendGrant && isBusiAudit && grantActive && !alreadySuspended"
          type="button"
          class="gov-btn gov-btn-secondary"
          @click="suspendGrant"
        >
          暂停授权
        </button>
        <button
          v-if="canRevokeGrant && isBusiAudit && grantActive"
          type="button"
          class="gov-btn gov-btn-danger"
          @click="revokeGrant"
        >
          收回授权
        </button>
        <button
          v-if="canRevokeGrant && isApplicant && grantActive"
          type="button"
          class="gov-btn gov-btn-danger"
          @click="abandonGrant"
        >
          我不再需要
        </button>
      </DetailActions>
    </section>
  </main>
</template>

<style scoped>
.gov-btn { padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; border: 1px solid transparent; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
.gov-btn-primary:disabled { background: #9bbedd; cursor: not-allowed; opacity: 0.85; }
.gov-btn-secondary { background: #fff; border-color: var(--b-border, #d4e2f4); color: var(--b-neutral-text, #1a1d21); }
.gov-btn-danger { background: #fff; border-color: var(--b-danger, #d4380d); color: var(--b-danger, #d4380d); }
.gov-btn-danger:hover { background: var(--b-danger, #d4380d); color: #fff; }
.legacy-note { margin: 0 0 12px; padding: 8px 12px; font-size: 13px; color: var(--b-muted, #5c6370); background: #f5f7fa; border-radius: 6px; }
.aux-links { margin: 12px 0; font-size: 13px; }
.aux-links a { color: var(--b-primary, #006be6); text-decoration: none; }
.aux-links a:hover { text-decoration: underline; }
</style>
