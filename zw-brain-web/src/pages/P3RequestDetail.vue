<script setup lang="ts">
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import { lookupRequest, useSnapshot } from '@/composables/useSnapshot';
import { invokeActionStub } from '@/composables/useActionStub';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DetailPanel from '@/components/DetailPanel.vue';
import DetailActions from '@/components/DetailActions.vue';
import { mapDetailRows } from '@/lib/detailDisplay';

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
  if (req.value) return String(req.value.resourceName ?? req.value.purpose ?? '') || '—';
  if (source.value !== 'live') return '正在加载……';
  return '未找到该申请';
});

async function withdraw() {
  await invokeActionStub({ skillId: 'catalog.entry.withdraw', payload: { request_id: id.value }, successTitle: '已撤回', pendingBackend: 'E2' });
}
async function supplement() {
  await invokeActionStub({ skillId: 'application.resource.submit', payload: { request_id: id.value }, successTitle: '补件已提交', pendingBackend: 'E2 (e2/plan.yaml F4)' });
}
</script>

<template>
  <main class="focus-page focus-detail">
    <nav class="crumbs"><a href="#/request-flow">← 申请列表</a></nav>
    <section class="panel">
      <PageFocusHeader :title="id" :meta="headerMeta" />
      <DetailPanel v-if="rows.length" title="基本信息" :rows="rows" />
      <DetailPanel v-if="prefilled.length" title="系统预填字段" :rows="prefilled" />
      <DetailActions>
        <button type="button" class="gov-btn gov-btn-primary" @click="supplement">补件 / 重新提交</button>
        <button type="button" class="gov-btn gov-btn-secondary" @click="withdraw">撤回申请</button>
      </DetailActions>
    </section>
  </main>
</template>
