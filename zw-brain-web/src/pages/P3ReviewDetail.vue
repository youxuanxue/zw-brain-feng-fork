<script setup lang="ts">
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import { lookupRequest, useSnapshot } from '@/composables/useSnapshot';
import { invokeActionStub } from '@/composables/useActionStub';
import DetailPanel from '@/components/DetailPanel.vue';

const route = useRoute();
const id = computed(() => String(route.params.id ?? ''));
const req = lookupRequest(id.value);
const { source } = useSnapshot();

const rows = computed(() => {
  const r = req.value;
  if (!r) return [];
  return [
    { label: '申请编号', value: id.value },
    { label: '资源', value: String(r.resourceName ?? '—') },
    { label: '申请人', value: String(r.applicant ?? '—') },
    { label: '用途', value: String(r.purpose ?? '—') },
    { label: '当前状态', value: String(r.status ?? '—') },
  ];
});

async function approve() {
  await invokeActionStub({ skillId: 'approval.case.decide', payload: { request_id: id.value, decision: 'approved' }, successTitle: '已通过', pendingBackend: 'E2 审批 (e2/plan.yaml F4)' });
}
async function reject() {
  await invokeActionStub({ skillId: 'approval.case.decide', payload: { request_id: id.value, decision: 'rejected' }, successTitle: '已驳回', pendingBackend: 'E2 审批' });
}
async function fix() {
  await invokeActionStub({ skillId: 'approval.case.decide', payload: { request_id: id.value, decision: 'pending-fix' }, successTitle: '已退回补正', pendingBackend: 'E2 审批' });
}
</script>

<template>
  <main class="page-shell">
    <nav class="crumbs"><a href="#/request-flow">← 回到申请列表</a></nav>
    <header class="page-hero">
      <div class="page-kicker">P3 · 审批面板</div>
      <h1 class="page-hero-title">审批 {{ id }}</h1>
      <p class="page-hero-subtitle">仅 ROLE_ORGAN_MANAGER / ROLE_BUSIAUDIT 可见。</p>
    </header>

    <DetailPanel v-if="rows.length" title="审批要点" :rows="rows" />

    <section v-if="!req && source === 'live'" class="panel">
      <p class="text-body text-zw-mute">未在 snapshot 中找到此申请。</p>
    </section>

    <section class="panel">
      <header><h2 class="panel-title">作出审批决定</h2><p class="panel-subtitle">人工动作不可绕过，三键互斥</p></header>
      <div class="actions">
        <button type="button" class="gov-btn gov-btn-primary" data-skill="approval.case.decide" @click="approve">通过</button>
        <button type="button" class="gov-btn gov-btn-secondary" data-skill="approval.case.decide" @click="fix">退回补正</button>
        <button type="button" class="gov-btn gov-btn-danger" data-skill="approval.case.decide" @click="reject">驳回</button>
      </div>
    </section>
  </main>
</template>

<style scoped>
.page-shell { display: grid; gap: 16px; }
.crumbs a { font-size: 13px; color: var(--b-primary, #006be6); text-decoration: none; }
.actions { display: flex; gap: 8px; margin-top: 12px; }
.gov-btn { padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; border: 1px solid transparent; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
.gov-btn-secondary { background: #fff; border-color: var(--b-border, #d4e2f4); color: var(--b-neutral-text, #1a1d21); }
.gov-btn-danger { background: #b32424; color: #fff; }
</style>
