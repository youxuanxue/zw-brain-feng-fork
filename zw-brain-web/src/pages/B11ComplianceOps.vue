<script setup lang="ts">
import { computed } from 'vue';
import { useDisputes, useAlerts, useSnapshot } from '@/composables/useSnapshot';
import { invokeActionStub, pushToast } from '@/composables/useActionStub';
import DrillStrip from '@/components/DrillStrip.vue';
import NLAcceleratorPanel from '@/components/NLAcceleratorPanel.vue';
import type { StructuredAction } from '@/composables/useNLAccelerator';

const NL_PRESETS_B11 = [
  '看本周高风险异议',
  '近 24h 审计失败',
  '溯源 REQ-2026-04-25-0011',
];

function consumeNLAction(action: StructuredAction) {
  // navigate kind 由 NLAcceleratorPanel 自身处理。
  // invoke 真调；filter/draft 先 toast 反馈，page-specific 注入留 E4 后端 land 后接线。
  if (action.kind === 'invoke' && action.target) {
    void invokeActionStub({ skillId: action.target, payload: action.payload, successTitle: action.label });
  } else if (action.kind === 'filter' || action.kind === 'draft') {
    pushToast({ kind: 'info', title: '已应用', detail: action.label });
  }
}

const disputes = useDisputes();
const alerts = useAlerts();
const { source } = useSnapshot();

const drillItems = computed(() => [
  { label: '回放审计链', href: '#/compliance-ops', hint: '事件 → 责任' },
  { label: '减负督查', href: '#/compliance-ops', hint: '抽查 / 绕行' },
]);

const disputeRows = computed(() =>
  disputes.value.slice(0, 10).map((d) => {
    const it = d as Record<string, unknown>;
    return {
      id: String(it.id ?? ''),
      title: String(it.title ?? it.subject ?? ''),
      status: String(it.status ?? ''),
    };
  })
);
const alertRows = computed(() =>
  alerts.value.slice(0, 10).map((a) => {
    const it = a as Record<string, unknown>;
    return {
      id: String(it.id ?? ''),
      title: String(it.title ?? it.label ?? ''),
      desc: String(it.desc ?? it.note ?? ''),
    };
  })
);

async function escalate(id: string) {
  await invokeActionStub({
    skillId: 'governance.dispute.escalate',
    payload: { dispute_id: id },
    successTitle: '已升级处理',
    pendingBackend: 'E4 后台业务 (e4/plan.yaml F3)',
  });
}
async function resolve(id: string) {
  await invokeActionStub({
    skillId: 'governance.dispute.resolve',
    payload: { dispute_id: id },
    successTitle: '已标记解决',
    pendingBackend: 'E4 后台业务 (e4/plan.yaml F3)',
  });
}
</script>

<template>
  <main class="page-shell">
    <header class="page-hero">
      <div class="hero-row">
        <div>
          <div class="page-kicker">B1.1 · 后台支撑面</div>
          <h1 class="page-hero-title">合规与运营</h1>
          <p class="page-hero-subtitle">审计回放 / 统计 / 异常 / 追责；仅管理员 / 审计员。</p>
        </div>
        <NLAcceleratorPanel page-anchor="B1.1" :presets="NL_PRESETS_B11" @action="consumeNLAction" />
      </div>
    </header>

    <DrillStrip kicker="高频任务" :items="drillItems" />

    <section class="panel">
      <header>
        <h2 class="panel-title">异议工单</h2>
        <p class="panel-subtitle">F3 阶段：列表 + 升级 / 解决 stub；详情走子页</p>
      </header>
      <table v-if="source === 'live' && disputeRows.length" class="ops-table">
        <thead><tr><th>编号</th><th>标题</th><th>状态</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="d in disputeRows" :key="d.id">
            <td><a :href="`#/compliance-ops/dispute/${d.id}`"><code>{{ d.id }}</code></a></td>
            <td>{{ d.title || '—' }}</td>
            <td><span class="status-pill">{{ d.status }}</span></td>
            <td class="actions">
              <button type="button" class="gov-btn gov-btn-secondary" data-skill="governance.dispute.escalate" @click="escalate(d.id)">升级</button>
              <button type="button" class="gov-btn gov-btn-primary" data-skill="governance.dispute.resolve" @click="resolve(d.id)">标记解决</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-else-if="source === 'live'" class="text-body text-zw-mute">当前无异议工单。</div>
      <div v-else class="text-body text-zw-mute">等待 /api/snapshot 装载工单。</div>
    </section>

    <section class="panel">
      <header>
        <h2 class="panel-title">告警事件</h2>
        <p class="panel-subtitle">最新 10 条，点击进入合规细查（F3 子页留 PagePlaceholder）</p>
      </header>
      <ul v-if="alertRows.length" class="alert-list">
        <li v-for="a in alertRows" :key="a.id || a.title">
          <strong>{{ a.title }}</strong>
          <em v-if="a.desc">{{ a.desc }}</em>
        </li>
      </ul>
      <div v-else class="text-body text-zw-mute">当前无告警。</div>
    </section>
  </main>
</template>

<style scoped>
.page-shell { display: grid; gap: 16px; }
.hero-row { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.ops-table { width: 100%; border-collapse: collapse; margin-top: 12px; }
.ops-table th, .ops-table td { padding: 10px 8px; text-align: left; font-size: 13px; border-bottom: 1px solid var(--b-border, #d4e2f4); }
.ops-table th { background: var(--b-bg-subtle, #e8f2fc); color: var(--b-muted, #5c6370); font-weight: 600; }
.ops-table code { background: var(--b-bg-subtle, #e8f2fc); padding: 2px 6px; border-radius: 4px; }
.status-pill { background: var(--b-bg-subtle, #e8f2fc); color: var(--b-primary, #006be6); font-size: 12px; padding: 2px 8px; border-radius: 999px; }
.actions { display: flex; gap: 6px; }
.gov-btn { padding: 4px 10px; border-radius: 6px; font-size: 12px; cursor: pointer; border: 1px solid transparent; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
.gov-btn-secondary { background: #fff; border-color: var(--b-border, #d4e2f4); color: var(--b-neutral-text, #1a1d21); }
.alert-list { list-style: none; padding: 0; margin: 12px 0 0; }
.alert-list li { padding: 8px 0; border-bottom: 1px dashed var(--b-border, #d4e2f4); font-size: 13px; }
.alert-list em { display: block; font-style: normal; font-size: 12px; color: var(--b-muted, #5c6370); margin-top: 4px; }
</style>
