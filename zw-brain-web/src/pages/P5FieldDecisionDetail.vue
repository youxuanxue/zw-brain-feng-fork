<script setup lang="ts">
import { computed, ref } from 'vue';
import { useRoute } from 'vue-router';
import { invokeActionStub, pushToast } from '@/composables/useActionStub';
import { getProductRole } from '@/composables/useProductRole';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DetailPanel from '@/components/DetailPanel.vue';
import DetailActions from '@/components/DetailActions.vue';
import { useProvider } from '@/composables/useSnapshot';
import { mapDetailRows } from '@/lib/detailDisplay';
import { canPerformAction } from '@/lib/pageAccess';
import { deriveFieldDecisions } from '@/lib/providerProjection';
import { formatTodoStatus } from '@/lib/statusLabels';
import { shortId } from '@/lib/userLanguage';

const route = useRoute();
const role = getProductRole();
const provider = useProvider();
const id = computed(() => String(route.params.id ?? ''));
// 两级管线第一级：反向编目草稿的部门审（confirm/reject）= 部门管理员；
// 与后端 policy set-equal（ACTION_ROLE_GATES 单源）。平台审在目录审核收件箱（业务运营员）。
const canDecide = computed(() => canPerformAction('catalog.entry.reverse_draft.confirm', role.value));

// 被审内容来自部门审收件箱同一投影（去盲批，同审核口径）：
// 目录名 / 责任单位 / 当前状态 / 字段建议数全取真实登记，缺省诚实「—」，不再捏造
// 「范围/处理时限」虚构行。
const inboxRow = computed(() =>
  deriveFieldDecisions(provider.value as Record<string, unknown>).find((r) => r.id === id.value),
);

const rows = computed(() => {
  const row = inboxRow.value;
  return mapDetailRows([
    { label: '审核编号', value: shortId(id.value) },
    { label: '目录名称', value: row?.title || '—' },
    { label: '责任单位', value: row?.detail?.owner || '—' },
    { label: '当前状态', value: row ? formatTodoStatus(row.status) : '—' },
    { label: '字段建议', value: row?.detail ? `${row.detail.fieldCount} 条` : '—' },
    { label: '目录编码', value: id.value },
  ]);
});

async function approve() {
  if (!canDecide.value) {
    pushToast({
      kind: 'info',
      title: '暂无审核权限',
      detail: '反向编目草稿的部门审由部门管理员办理；通过后转业务运营员平台审。',
    });
    return;
  }
  await invokeActionStub({
    skillId: 'catalog.entry.reverse_draft.confirm',
    payload: { catalog_code: id.value },
    successTitle: '已通过部门审，转平台审',
  });
}

// 驳回带理由：先点「驳回」展开理由框，填写后确认提交。
// 注意：反向编目「驳回」= 草稿终态枪毙（后端 catalog_entry.py reverse_draft.reject
// 落 rejected，无回 draft 路径），不是退回补证重提；理由仅作终止凭据，
// 文案不得承诺「重新提交」。要退回补证应走另一语义的挂接审核 return_for_fix，不在此页。
const rejecting = ref(false);
const rejectReason = ref('');
function startReject() {
  if (!canDecide.value) {
    pushToast({
      kind: 'info',
      title: '暂无审核权限',
      detail: '反向编目草稿的部门审由部门管理员办理。',
    });
    return;
  }
  rejecting.value = true;
  rejectReason.value = '';
}
function cancelReject() {
  rejecting.value = false;
  rejectReason.value = '';
}

async function confirmReject() {
  if (!rejectReason.value.trim()) {
    pushToast({ kind: 'warn', title: '请填写驳回理由', detail: '驳回将终止本反向编目草稿（不可重提），需要说明依据。' });
    return;
  }
  await invokeActionStub({
    skillId: 'catalog.entry.reverse_draft.reject',
    payload: { catalog_code: id.value, reject_reason: rejectReason.value.trim() },
    successTitle: '已驳回',
  });
  cancelReject();
}
</script>

<template>
  <main class="focus-page focus-detail">
    <nav class="crumbs"><a href="#/provider/inbox/field-decision">← 反向编目审核收件箱</a></nav>
    <section class="panel">
      <PageFocusHeader :title="`反向编目审核 ${shortId(id)}`" meta="部门审通过后转业务运营员平台审；提交后进入审计链，不可静默撤销" />
      <DetailPanel title="被审反向编目草稿" :rows="rows" />
      <p v-if="!canDecide" class="role-hint">当前岗位无权在此审核；反向编目草稿的部门审由部门管理员办理。</p>
      <DetailActions v-if="canDecide && !rejecting">
        <button type="button" class="gov-btn gov-btn-primary" @click="approve">通过审核</button>
        <button type="button" class="gov-btn gov-btn-danger" data-testid="field-decision-reject-btn" @click="startReject">驳回</button>
      </DetailActions>
      <div v-if="canDecide && rejecting" class="reject-box" data-testid="field-decision-reject-panel">
        <label for="field-decision-reject-reason">驳回理由（草稿终止受理，不可重提）</label>
        <textarea
          id="field-decision-reject-reason"
          v-model="rejectReason"
          rows="3"
          placeholder="请说明目录口径 / 字段不成立的依据，作为终止受理的凭据"
        />
        <div class="reject-actions">
          <button type="button" class="gov-btn gov-btn-danger" data-testid="field-decision-reject-confirm-btn" @click="confirmReject">确认驳回</button>
          <button type="button" class="gov-btn" @click="cancelReject">取消</button>
        </div>
      </div>
    </section>
  </main>
</template>

<style scoped>
.gov-btn { padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; border: 1px solid transparent; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
.gov-btn-danger { background: #fff; border-color: #cf1322; color: #cf1322; }
.role-hint { font-size: 13px; color: var(--b-muted, #5c6370); margin: 8px 0 12px; }
.reject-box { display: grid; gap: 8px; max-width: 640px; padding: 8px 0 4px; }
.reject-box label { font-size: 13px; color: var(--b-muted, #5c6370); }
.reject-box textarea { width: 100%; padding: 8px 10px; border: 1px solid var(--b-border, #d4e2f4); border-radius: 6px; font-size: 13px; }
.reject-actions { display: flex; gap: 10px; }
</style>
