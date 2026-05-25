<script setup lang="ts">
import { computed } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import { useRequests, useApprovals, useSnapshot } from '@/composables/useSnapshot';
import { invokeActionStub, pushToast } from '@/composables/useActionStub';
import NLAcceleratorPanel from '@/components/NLAcceleratorPanel.vue';
import type { StructuredAction } from '@/composables/useNLAccelerator';
import { formatTodoStatus, todoStatusTone } from '@/lib/statusLabels';

const NL_PRESETS_P3 = ['我待审的有几条', '催办昨天提交的申请', '驳回所有 30 天未跟进'];

function consumeNLAction(action: StructuredAction) {
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

const headerMeta = computed(() => {
  if (source.value !== 'live') return '正在加载……';
  const n = items.value.length;
  const pending = approvals.value.length;
  return n
    ? `${n} 条在途${pending ? ` · 待审 ${pending} 条` : ''}`
    : '暂无在途申请，可从资源发现发起';
});

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
  <main class="focus-page">
    <section class="panel">
      <PageFocusHeader
        title="在途申请"
        :meta="headerMeta"
        :links="[
          { label: '资源发现', href: '#/discovery' },
          { label: '交付回执', href: '#/delivery-exchange' },
        ]"
      >
        <template #aside>
          <NLAcceleratorPanel page-anchor="P3" :presets="NL_PRESETS_P3" @action="consumeNLAction" />
        </template>
      </PageFocusHeader>

      <table v-if="source === 'live' && items.length" class="focus-table">
        <thead>
          <tr><th>编号</th><th>资源</th><th>用途</th><th>状态</th><th>提交时间</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="it in items" :key="it.id">
            <td><a :href="`#/request-flow/request/${it.id}`"><code>{{ it.id }}</code></a></td>
            <td>{{ it.resource || '—' }}</td>
            <td>{{ it.title || '—' }}</td>
            <td>
              <span class="status-pill" :class="todoStatusTone(it.status)">{{ formatTodoStatus(it.status) }}</span>
            </td>
            <td>{{ it.submittedAt || '—' }}</td>
            <td class="table-actions">
              <div class="table-actions-inner">
                <button type="button" class="gov-btn gov-btn-secondary" @click="viewReview(it.id)">查看</button>
                <button type="button" class="gov-btn gov-btn-primary" @click="quickResubmit(it.id)">重新提交</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else-if="source === 'live'" class="focus-empty">暂无在途申请。</p>
      <p v-else class="focus-empty">等待数据装载……</p>
    </section>
  </main>
</template>

<style scoped>
.gov-btn { padding: 4px 10px; border-radius: 6px; font-size: 12px; cursor: pointer; border: 1px solid transparent; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
.gov-btn-secondary { background: #fff; border-color: var(--b-border, #d4e2f4); }
</style>
