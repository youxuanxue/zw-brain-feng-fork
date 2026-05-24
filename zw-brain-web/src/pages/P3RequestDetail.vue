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
  const out: { label: string; value: string }[] = [];
  if (r.resourceName) out.push({ label: '复用资源', value: String(r.resourceName) });
  if (r.applicant) out.push({ label: '申请人', value: String(r.applicant) });
  if (r.applicantDept) out.push({ label: '申请部门', value: String(r.applicantDept) });
  if (r.purpose) out.push({ label: '使用用途', value: String(r.purpose) });
  if (r.range) out.push({ label: '覆盖范围', value: String(r.range) });
  if (r.status) out.push({ label: '当前状态', value: String(r.status) });
  if (r.submittedAt) out.push({ label: '提交时间', value: String(r.submittedAt) });
  if (r.expectedBy) out.push({ label: '期望完成', value: String(r.expectedBy) });
  if (r.auditId) out.push({ label: '审计 ID', value: String(r.auditId) });
  return out;
});

const prefilled = computed(() => {
  const arr = req.value?.prefilledFields;
  if (!Array.isArray(arr)) return [];
  return (arr as Record<string, unknown>[]).map((it) => ({
    label: String(it.label ?? ''),
    value: String(it.value ?? ''),
    source: String(it.source ?? ''),
    state: String(it.state ?? ''),
  }));
});

async function withdraw() {
  await invokeActionStub({ skillId: 'catalog.entry.withdraw', payload: { request_id: id.value }, successTitle: '已撤回', pendingBackend: 'E2' });
}
async function supplement() {
  await invokeActionStub({ skillId: 'application.resource.submit', payload: { request_id: id.value }, successTitle: '补件已提交', pendingBackend: 'E2 (e2/plan.yaml F4)' });
}
</script>

<template>
  <main class="page-shell">
    <nav class="crumbs"><a href="#/request-flow">← 回到申请列表</a></nav>
    <header class="page-hero">
      <div class="page-kicker">P3 · 申请详情</div>
      <h1 class="page-hero-title">{{ id }}</h1>
      <p v-if="req" class="page-hero-subtitle">{{ String(req.purpose ?? '') || '—' }}</p>
      <p v-else-if="source !== 'live'" class="page-hero-subtitle">等待 /api/snapshot 装载该申请。</p>
      <p v-else class="page-hero-subtitle">当前 snapshot 中未找到此申请，可能已归档或权限不足。</p>
    </header>

    <DetailPanel v-if="rows.length" title="基本信息" subtitle="来自 /api/snapshot::requests" :rows="rows" />

    <section v-if="prefilled.length" class="panel">
      <header>
        <h2 class="panel-title">系统预填字段</h2>
        <p class="panel-subtitle">「先复用模板再补差异字段」自动化结果</p>
      </header>
      <DetailPanel title="" :rows="prefilled" />
    </section>

    <section class="panel">
      <header><h2 class="panel-title">下一步</h2></header>
      <div class="actions">
        <button type="button" class="gov-btn gov-btn-primary" data-skill="application.resource.submit" @click="supplement">补件 / 重新提交</button>
        <button type="button" class="gov-btn gov-btn-secondary" data-skill="catalog.entry.withdraw" @click="withdraw">撤回申请</button>
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
</style>
