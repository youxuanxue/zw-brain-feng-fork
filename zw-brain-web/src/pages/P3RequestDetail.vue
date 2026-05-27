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
import { mapDetailRows } from '@/lib/detailDisplay';
import { formatTodoStatus } from '@/lib/statusLabels';

const route = useRoute();
const id = computed(() => String(route.params.id ?? ''));
const req = lookupRequest(id.value);
const { source } = useSnapshot();

const rows = computed(() => {
  const r = req.value;
  if (!r) return [];
  const raw: { label: string; value: string; state?: string; source?: string }[] = [];
  if (r.resourceName) raw.push({ label: '复用资源', value: String(r.resourceName) });
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
// request.submit 仅 OPERATER；MANAGER 进申请详情时不渲染「补件 / 重新提交」按钮
const canSubmitRequest = computed(() => canPerformAction('request.submit', getProductRole().value));
const canResubmit = computed(() => rawStatus.value === 'need-fix');
const canWithdraw = computed(() => ['pending', 'need-fix', 'draft'].includes(rawStatus.value));

async function withdraw() {
  pushToast({
    kind: 'info',
    title: '暂不可撤回',
    detail: canWithdraw.value
      ? '撤回申请能力尚未在本环境开通；如需取消请联系审批人驳回或等待退回补正。'
      : '当前状态不支持撤回申请。',
  });
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
      <DetailPanel v-if="prefilled.length" title="系统预填字段" :rows="prefilled" />
      <p class="aux-links">
        <a href="#/request-flow/objection">我的异议</a>
        ·
        <a href="#/request-flow/supply-demand">找不到数据 · 登记需求</a>
      </p>
      <DetailActions>
        <button
          v-if="canSubmitRequest"
          type="button"
          class="gov-btn gov-btn-primary"
          @click="supplement"
        >
          补件 / 重新提交
        </button>
        <button type="button" class="gov-btn gov-btn-secondary" @click="withdraw">撤回申请</button>
      </DetailActions>
    </section>
  </main>
</template>

<style scoped>
.gov-btn { padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; border: 1px solid transparent; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
.gov-btn-primary:disabled { background: #9bbedd; cursor: not-allowed; opacity: 0.85; }
.gov-btn-secondary { background: #fff; border-color: var(--b-border, #d4e2f4); color: var(--b-neutral-text, #1a1d21); }
.aux-links { margin: 12px 0; font-size: 13px; }
.aux-links a { color: var(--b-primary, #006be6); text-decoration: none; }
.aux-links a:hover { text-decoration: underline; }
</style>
