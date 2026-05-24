<script setup lang="ts">
import { computed } from 'vue';
import { useRequests, useApprovals, useSnapshot } from '@/composables/useSnapshot';
import { invokeActionStub, pushToast } from '@/composables/useActionStub';
import DrillStrip from '@/components/DrillStrip.vue';
import NLAcceleratorPanel from '@/components/NLAcceleratorPanel.vue';
import type { StructuredAction } from '@/composables/useNLAccelerator';

const NL_PRESETS_P3 = [
  '我待审的有几条',
  '催办昨天提交的申请',
  '驳回所有 30 天未跟进',
];

function consumeNLAction(action: StructuredAction) {
  // navigate kind 由 NLAcceleratorPanel 自身处理（window.location.hash）。
  // invoke 真调；filter/draft 先 toast 反馈，page-specific filter/form 注入留 E2 land 后接线。
  if (action.kind === 'invoke' && action.target) {
    void invokeActionStub({ skillId: action.target, payload: action.payload, successTitle: action.label });
  } else if (action.kind === 'filter' || action.kind === 'draft') {
    pushToast({ kind: 'info', title: '已应用', detail: action.label });
  }
}

const requests = useRequests();
const approvals = useApprovals();
const { source } = useSnapshot();
const items = computed(() =>
  requests.value.map((r) => {
    const it = r as Record<string, unknown>;
    return {
      id: String(it.id ?? ''),
      title: String(it.purpose ?? it.title ?? ''),
      resource: String(it.resourceName ?? it.resource_id ?? ''),
      status: String(it.status ?? ''),
      submittedAt: String(it.submittedAt ?? ''),
    };
  })
);
const drillItems = computed(() => [
  { label: '待我审批', href: '#/request-flow', hint: `审批队列 ${approvals.value.length}` },
  { label: '回到发现', href: '#/discovery', hint: '从资源起申请' },
  { label: '查看交付', href: '#/delivery-exchange', hint: '看回执' },
]);

async function viewReview(id: string) {
  window.location.hash = `#/request-flow/review/${id}`;
}
async function quickResubmit(id: string) {
  await invokeActionStub({
    skillId: 'request.submit',
    payload: { request_id: id },
    successTitle: '已重新提交',
    pendingBackend: 'E2 申请管理 (e2/plan.yaml F4)',
  });
}
</script>

<template>
  <main class="page-shell">
    <header class="page-hero">
      <div class="hero-row">
        <div>
          <div class="page-kicker">P3 · J1 找数→用数</div>
          <h1 class="page-hero-title">申请 · 审批 · 跟踪</h1>
          <p class="page-hero-subtitle">受控准入：发起、补件、审核、回执、进度。</p>
        </div>
        <NLAcceleratorPanel page-anchor="P3" :presets="NL_PRESETS_P3" @action="consumeNLAction" />
      </div>
    </header>

    <DrillStrip kicker="按角色优先动作" :items="drillItems" />

    <section class="panel">
      <header>
        <h2 class="panel-title">在途申请</h2>
        <p class="panel-subtitle">含有条件 / 无条件共享审批分支</p>
      </header>
      <table v-if="source === 'live' && items.length" class="req-table">
        <thead>
          <tr><th>编号</th><th>资源</th><th>用途</th><th>状态</th><th>提交时间</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="it in items" :key="it.id">
            <td><a :href="`#/request-flow/request/${it.id}`"><code>{{ it.id }}</code></a></td>
            <td>{{ it.resource || '—' }}</td>
            <td>{{ it.title || '—' }}</td>
            <td><span class="status-pill">{{ it.status }}</span></td>
            <td>{{ it.submittedAt || '—' }}</td>
            <td class="actions">
              <button type="button" class="gov-btn gov-btn-secondary" data-skill="request.view" @click="viewReview(it.id)">查看</button>
              <button type="button" class="gov-btn gov-btn-primary" data-skill="request.submit" @click="quickResubmit(it.id)">重新提交</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-else-if="source === 'live'" class="text-body text-zw-mute">暂无在途申请。从 P2 资源发现起一条。</div>
      <div v-else class="text-body text-zw-mute">等待 /api/snapshot 装载在途申请。</div>
    </section>
  </main>
</template>

<style scoped>
.page-shell { display: grid; gap: 16px; }
.hero-row { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.req-table { width: 100%; border-collapse: collapse; margin-top: 12px; }
.req-table th, .req-table td { padding: 10px 8px; text-align: left; font-size: 13px; border-bottom: 1px solid var(--b-border, #d4e2f4); }
.req-table th { background: var(--b-bg-subtle, #e8f2fc); color: var(--b-muted, #5c6370); font-weight: 600; }
.req-table code { background: var(--b-bg-subtle, #e8f2fc); padding: 2px 6px; border-radius: 4px; }
.status-pill { background: var(--b-bg-subtle, #e8f2fc); color: var(--b-primary, #006be6); font-size: 12px; padding: 2px 8px; border-radius: 999px; }
.actions { display: flex; gap: 6px; }
.gov-btn { padding: 4px 10px; border-radius: 6px; font-size: 12px; cursor: pointer; border: 1px solid transparent; text-decoration: none; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
.gov-btn-secondary { background: #fff; border-color: var(--b-border, #d4e2f4); color: var(--b-neutral-text, #1a1d21); }
</style>
