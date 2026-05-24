<script setup lang="ts">
import { computed } from 'vue';
import { useProvider, useSnapshot } from '@/composables/useSnapshot';
import { invokeActionStub } from '@/composables/useActionStub';
import DrillStrip from '@/components/DrillStrip.vue';

const provider = useProvider();
const { source } = useSnapshot();

const counts = computed(() => {
  const it = provider.value as Record<string, unknown>;
  const fieldDec = Array.isArray((it as { field_decisions?: unknown[] }).field_decisions)
    ? ((it as { field_decisions: unknown[] }).field_decisions).length
    : 0;
  const hookup = Array.isArray((it as { hookup_reviews?: unknown[] }).hookup_reviews)
    ? ((it as { hookup_reviews: unknown[] }).hookup_reviews).length
    : 0;
  const demand = Array.isArray((it as { demand_matches?: unknown[] }).demand_matches)
    ? ((it as { demand_matches: unknown[] }).demand_matches).length
    : 0;
  const catalogs = Array.isArray((it as { catalogs?: unknown[] }).catalogs)
    ? ((it as { catalogs: unknown[] }).catalogs).length
    : 0;
  const services = Array.isArray((it as { services?: unknown[] }).services)
    ? ((it as { services: unknown[] }).services).length
    : 0;
  return [
    { key: 'field-decision', label: '字段裁决', value: fieldDec, href: '#/provider/inbox/field-decision' },
    { key: 'hookup-review', label: '挂接审核', value: hookup, href: '#/provider/inbox/hookup-review' },
    { key: 'demand-match', label: '供需对接', value: demand, href: '#/provider/inbox/demand-match' },
    { key: 'catalogs', label: '我的目录', value: catalogs, href: '#/provider' },
    { key: 'services', label: '已上架服务', value: services, href: '#/provider' },
  ];
});

const drillItems = computed(() => [
  { label: '反向编目', href: '#/provider/wizard/reverse-catalog', hint: '从已有库表生成草稿' },
  { label: 'API 服务化', href: '#/provider/wizard/api-service', hint: '一键上架受控 API' },
  { label: '质量规则', href: '#/provider/wizard/quality-rule', hint: '设定回流口径' },
]);

async function publishDraft(slug: string) {
  await invokeActionStub({
    skillId: 'catalog.entry.publish',
    payload: { entry_id: slug },
    successTitle: '已提交发布审核',
    pendingBackend: 'E4 提供方治理 (e4/plan.yaml F2)',
  });
}
</script>

<template>
  <main class="page-shell">
    <header class="page-hero">
      <div class="page-kicker">P5 · J2 挂数→维数</div>
      <h1 class="page-hero-title">提供方管理</h1>
      <p class="page-hero-subtitle">反向编目 / 资源挂接 / 服务上架；发布时重复率检测提醒（不硬拦）。</p>
    </header>

    <DrillStrip kicker="按操作类型" :items="drillItems" />

    <section class="panel">
      <header>
        <h2 class="panel-title">收件箱与资产概览</h2>
        <p class="panel-subtitle">F3 阶段：状态卡 + 跳子页 + 发布动作 stub</p>
      </header>
      <div v-if="source === 'live'">
        <div class="stat-grid">
          <a v-for="c in counts" :key="c.key" :href="c.href" class="stat-card">
            <strong>{{ c.value }}</strong>
            <em>{{ c.label }}</em>
          </a>
        </div>
        <div class="actions">
          <button type="button" class="gov-btn gov-btn-primary" data-skill="catalog.entry.publish" @click="publishDraft('demo-draft-001')">
            示例：提交草稿到发布审核
          </button>
        </div>
      </div>
      <div v-else class="text-body text-zw-mute">等待 /api/snapshot 装载提供方数据。</div>
    </section>
  </main>
</template>

<style scoped>
.page-shell { display: grid; gap: 16px; }
.stat-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 10px; margin-top: 12px; }
.stat-card { display: grid; gap: 4px; padding: 14px; border: 1px solid var(--b-border, #d4e2f4); border-radius: 8px; text-decoration: none; color: inherit; background: #fff; }
.stat-card strong { font-size: 22px; color: var(--b-primary, #006be6); }
.stat-card em { font-style: normal; font-size: 13px; color: var(--b-muted, #5c6370); }
.stat-card:hover { background: var(--b-bg-subtle, #e8f2fc); }
.actions { margin-top: 16px; }
.gov-btn { padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; border: 1px solid transparent; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
</style>
