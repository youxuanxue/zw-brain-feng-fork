<script setup lang="ts">
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import { invokeActionStub, pushToast } from '@/composables/useActionStub';
import { getProductRole } from '@/composables/useProductRole';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DetailPanel from '@/components/DetailPanel.vue';
import DetailActions from '@/components/DetailActions.vue';
import { mapDetailRows } from '@/lib/detailDisplay';
import { canDecideFieldDrafts } from '@/lib/requestFlowRoles';

const route = useRoute();
const role = getProductRole();
const id = computed(() => String(route.params.id ?? ''));
const canDecide = computed(() => canDecideFieldDrafts(role.value));

const rows = computed(() =>
  mapDetailRows([
    { label: '裁决编号', value: id.value },
    { label: '目录编码', value: id.value },
    { label: '范围', value: '山东省 sd-default' },
    { label: '处理时限', value: '5 个工作日' },
  ]),
);

async function approve() {
  if (!canDecide.value) {
    pushToast({
      kind: 'info',
      title: '暂无裁决权限',
      detail: '字段口径裁决由业务运营员办理；部门管理员请在反向编目向导创建草稿。',
    });
    return;
  }
  await invokeActionStub({
    skillId: 'catalog.entry.reverse_draft.confirm',
    payload: { catalog_code: id.value },
    successTitle: '已通过',
    role: 'ROLE_BUSIAUDIT',
  });
}

async function reject() {
  if (!canDecide.value) {
    pushToast({
      kind: 'info',
      title: '暂无裁决权限',
      detail: '字段口径裁决由业务运营员办理。',
    });
    return;
  }
  await invokeActionStub({
    skillId: 'catalog.entry.reverse_draft.reject',
    payload: { catalog_code: id.value, reject_reason: '字段口径需补充证据后重新提交' },
    successTitle: '已驳回',
    role: 'ROLE_BUSIAUDIT',
  });
}
</script>

<template>
  <main class="focus-page focus-detail">
    <nav class="crumbs"><a href="#/provider/inbox/field-decision">← 字段裁决收件箱</a></nav>
    <section class="panel">
      <PageFocusHeader :title="`裁决 ${id}`" meta="提交后进入审计链，不可静默撤销" />
      <DetailPanel title="基本信息" :rows="rows" />
      <p v-if="!canDecide" class="role-hint">当前岗位无权在此裁决；请切换为业务运营员。</p>
      <DetailActions v-if="canDecide">
        <button type="button" class="gov-btn gov-btn-primary" @click="approve">通过裁决</button>
        <button type="button" class="gov-btn gov-btn-danger" @click="reject">驳回</button>
      </DetailActions>
    </section>
  </main>
</template>

<style scoped>
.gov-btn { padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; border: 1px solid transparent; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
.gov-btn-danger { background: #fff; border-color: #cf1322; color: #cf1322; }
.role-hint { font-size: 13px; color: var(--b-muted, #5c6370); margin: 8px 0 12px; }
</style>
