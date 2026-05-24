<script setup lang="ts">
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import { invokeActionStub } from '@/composables/useActionStub';
import DetailPanel from '@/components/DetailPanel.vue';

const route = useRoute();
const id = computed(() => String(route.params.id ?? ''));

const rows = computed(() => [
  { label: '裁决编号', value: id.value },
  { label: '范围', value: 'sd-default 单租户单省（山东）' },
  { label: '提交角色', value: 'ROLE_ORGAN_MANAGER' },
  { label: '处理时限', value: '5 个工作日（业务方反馈 #11 配置）' },
]);

async function commit(decision: 'approve' | 'reject') {
  await invokeActionStub({
    skillId: 'catalog.entry.reverse_draft.confirm',
    payload: { id: id.value, decision },
    successTitle: decision === 'approve' ? '已通过' : '已驳回',
    pendingBackend: 'E4 提供方治理 (e4/plan.yaml F2)',
  });
}
</script>

<template>
  <main class="page-shell">
    <nav class="crumbs"><a href="#/provider">← 回到提供方收件箱</a></nav>
    <header class="page-hero">
      <div class="page-kicker">P5 · 字段裁决详情</div>
      <h1 class="page-hero-title">裁决 {{ id }}</h1>
      <p class="page-hero-subtitle">仅 ROLE_BUSIAUDIT；裁决一旦提交进入审计链，不可静默撤销。</p>
    </header>

    <DetailPanel title="基本信息" :rows="rows" />

    <section class="panel">
      <header><h2 class="panel-title">裁决</h2></header>
      <div class="actions">
        <button type="button" class="gov-btn gov-btn-primary" data-skill="catalog.entry.reverse_draft.confirm" @click="commit('approve')">通过裁决</button>
        <button type="button" class="gov-btn gov-btn-danger" data-skill="catalog.entry.reverse_draft.reject" @click="commit('reject')">驳回</button>
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
.gov-btn-danger { background: #b32424; color: #fff; }
</style>
