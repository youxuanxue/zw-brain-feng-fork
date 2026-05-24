<script setup lang="ts">
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import { lookupDispute, useSnapshot } from '@/composables/useSnapshot';
import { invokeActionStub } from '@/composables/useActionStub';
import DetailPanel from '@/components/DetailPanel.vue';

const route = useRoute();
const id = computed(() => String(route.params.id ?? ''));
const dispute = lookupDispute(id.value);
const { source } = useSnapshot();

const rows = computed(() => {
  const d = dispute.value;
  if (!d) return [{ label: '工单编号', value: id.value }];
  return [
    { label: '工单编号', value: id.value },
    { label: '标题', value: String(d.title ?? '—') },
    { label: '当前状态', value: String(d.status ?? '—') },
    { label: '相关资源', value: String(d.resource_id ?? d.resource_name ?? '—') },
    { label: '受理时间', value: String(d.opened_at ?? '—') },
  ];
});

async function escalate() {
  await invokeActionStub({ skillId: 'governance.dispute.escalate', payload: { dispute_id: id.value }, successTitle: '已升级', pendingBackend: 'E4 后台业务 (e4/plan.yaml F3)' });
}
async function resolve() {
  await invokeActionStub({ skillId: 'governance.dispute.resolve', payload: { dispute_id: id.value }, successTitle: '已解决', pendingBackend: 'E4 后台业务' });
}
</script>

<template>
  <main class="page-shell">
    <nav class="crumbs"><a href="#/compliance-ops">← 回到合规与运营</a></nav>
    <header class="page-hero">
      <div class="page-kicker">B1.1 · 异议详情</div>
      <h1 class="page-hero-title">{{ id }}</h1>
      <p v-if="!dispute && source === 'live'" class="page-hero-subtitle">当前 snapshot 中无此异议工单（disputes 列表为空属正常 dev 数据态）。</p>
    </header>

    <DetailPanel title="基本信息" :rows="rows" />

    <section class="panel">
      <header><h2 class="panel-title">处置动作</h2></header>
      <div class="actions">
        <button type="button" class="gov-btn gov-btn-secondary" data-skill="governance.dispute.escalate" @click="escalate">升级</button>
        <button type="button" class="gov-btn gov-btn-primary" data-skill="governance.dispute.resolve" @click="resolve">标记解决</button>
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
