<script setup lang="ts">
import { computed } from 'vue';
import { useDeliveryTasks, useSnapshot } from '@/composables/useSnapshot';
import { invokeActionStub } from '@/composables/useActionStub';
import DrillStrip from '@/components/DrillStrip.vue';

const tasks = useDeliveryTasks();
const { source } = useSnapshot();
const items = computed(() =>
  tasks.value.map((t) => {
    const it = t as Record<string, unknown>;
    return {
      id: String(it.id ?? ''),
      name: String(it.name ?? ''),
      requestId: String(it.requestId ?? ''),
      channel: String(it.channel ?? ''),
      status: String(it.status ?? ''),
      updatedAt: String(it.updatedAt ?? ''),
    };
  })
);
const drillItems = computed(() => [
  { label: '凭据领取', href: '#/delivery-exchange', hint: '获取 API Key + 调用样例' },
  { label: '回到申请', href: '#/request-flow', hint: '看上游进度' },
  { label: '查看审计', href: '#/compliance-ops', hint: '回放责任链' },
]);

async function openCredential(reqId: string) {
  if (reqId) window.location.hash = `#/delivery-exchange/credential/${reqId}`;
}
async function reconcile(id: string) {
  await invokeActionStub({
    skillId: 'delivery.reconcile_receipt',
    payload: { task_id: id },
    successTitle: '已触发对账',
    pendingBackend: 'E2 交付对账 (e2/plan.yaml F5)',
  });
}
</script>

<template>
  <main class="page-shell">
    <header class="page-hero">
      <div class="page-kicker">P4 · J1 找数→用数</div>
      <h1 class="page-hero-title">交付 · 交换 · 直达</h1>
      <p class="page-hero-subtitle">交付渠道、任务状态、结果回执；凭据领取附调用样例。</p>
    </header>

    <DrillStrip kicker="按下一步动作" :items="drillItems" />

    <section class="panel">
      <header>
        <h2 class="panel-title">交付任务</h2>
        <p class="panel-subtitle">F3 阶段：列表 + 状态 + 操作 stub；详情见子页</p>
      </header>
      <table v-if="source === 'live' && items.length" class="task-table">
        <thead><tr><th>编号</th><th>名称</th><th>渠道</th><th>状态</th><th>更新</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="t in items" :key="t.id">
            <td><a :href="`#/delivery-exchange/task/${t.id}`"><code>{{ t.id }}</code></a></td>
            <td>{{ t.name || '—' }}</td>
            <td>{{ t.channel || '—' }}</td>
            <td><span class="status-pill">{{ t.status }}</span></td>
            <td>{{ t.updatedAt || '—' }}</td>
            <td class="actions">
              <button type="button" class="gov-btn gov-btn-secondary" data-skill="credential.query" @click="openCredential(t.requestId)">领凭据</button>
              <button type="button" class="gov-btn gov-btn-primary" data-skill="delivery.reconcile_receipt" @click="reconcile(t.id)">对账回执</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-else-if="source === 'live'" class="text-body text-zw-mute">暂无交付任务。</div>
      <div v-else class="text-body text-zw-mute">等待 /api/snapshot 装载交付任务。</div>
    </section>
  </main>
</template>

<style scoped>
.page-shell { display: grid; gap: 16px; }
.task-table { width: 100%; border-collapse: collapse; margin-top: 12px; }
.task-table th, .task-table td { padding: 10px 8px; text-align: left; font-size: 13px; border-bottom: 1px solid var(--b-border, #d4e2f4); }
.task-table th { background: var(--b-bg-subtle, #e8f2fc); color: var(--b-muted, #5c6370); font-weight: 600; }
.task-table code { background: var(--b-bg-subtle, #e8f2fc); padding: 2px 6px; border-radius: 4px; }
.status-pill { background: var(--b-bg-subtle, #e8f2fc); color: var(--b-primary, #006be6); font-size: 12px; padding: 2px 8px; border-radius: 999px; }
.actions { display: flex; gap: 6px; }
.gov-btn { padding: 4px 10px; border-radius: 6px; font-size: 12px; cursor: pointer; border: 1px solid transparent; text-decoration: none; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
.gov-btn-secondary { background: #fff; border-color: var(--b-border, #d4e2f4); color: var(--b-neutral-text, #1a1d21); }
</style>
