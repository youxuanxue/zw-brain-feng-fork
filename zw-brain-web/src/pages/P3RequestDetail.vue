<script setup lang="ts">
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import { lookupRequest, useSnapshot } from '@/composables/useSnapshot';
import { invokeActionStub, pushToast } from '@/composables/useActionStub';
import { getProductRole } from '@/composables/useProductRole';
import { canPerformAction } from '@/lib/pageAccess';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DetailPanel from '@/components/DetailPanel.vue';
import DetailActions from '@/components/DetailActions.vue';
import EditableFormPanel from '@/components/EditableFormPanel.vue';
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
  if (r.status) raw.push({ label: '当前状态', value: String(r.status) });
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
// request.submit = OPERATER + MANAGER（D57④）；BUSIAUDIT（受理岗）进申请详情时不渲染「确认提交 / 重新提交」
const canSubmitRequest = computed(() => canPerformAction('request.submit', getProductRole().value));
// 草稿态（0605#8）：从 P2「申请资源」生成的草稿单，用户在此查看无误后「确认提交申请」才进审批。
const isDraft = computed(() => rawStatus.value === 'draft');
const canResubmit = computed(() => rawStatus.value === 'need-fix');

// 撤回 / 暂停授权：write-critical。j1-credential-revoke 决策 A（已签字）——
// 撤回 = 业务运营员合规收回（收回授权）+ 申请人本人主动放弃（我不再需要,owner 校验在后端）；
// 暂停 = 业务运营员。MANAGER 已收回该权限,「无权 = 不可见」整段不渲染。
// 仅对已授权（granted）/ 交付中 / 暂停（suspended）的申请显示,避免对草稿/审批中误操作。
const productRole = computed(() => getProductRole().value);
const isBusiAudit = computed(() => productRole.value === 'ROLE_BUSIAUDIT');
const isApplicant = computed(() => productRole.value === 'ROLE_ORGAN_OPERATER');
const canRevokeGrant = computed(() => canPerformAction('application.grant.revoke', productRole.value));
const canSuspendGrant = computed(() => canPerformAction('application.grant.suspend', productRole.value));
const grantActive = computed(() => ['granted', 'in_delivery', 'suspended'].includes(rawStatus.value));
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
  await invokeActionStub({
    skillId: 'request.submit',
    payload: { request_id: id.value },
    successTitle: '已重新提交',
  });
}
</script>

<template>
  <main class="focus-page focus-detail">
    <nav class="crumbs"><a href="#/request-flow">← 申请列表</a></nav>
    <section class="panel">
      <PageFocusHeader :title="id" :meta="headerMeta" />
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
        v-if="canSubmitRequest || (canSuspendGrant && grantActive) || (canRevokeGrant && grantActive)"
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
.aux-links { margin: 12px 0; font-size: 13px; }
.aux-links a { color: var(--b-primary, #006be6); text-decoration: none; }
.aux-links a:hover { text-decoration: underline; }
</style>
