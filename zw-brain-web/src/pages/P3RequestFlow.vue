<script setup lang="ts">
import { computed } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import { useRequests, useApprovals, useSnapshot } from '@/composables/useSnapshot';
import { invokeActionStub, pushToast } from '@/composables/useActionStub';
import { getProductRole } from '@/composables/useProductRole';
import NLAcceleratorPanel from '@/components/NLAcceleratorPanel.vue';
import type { StructuredAction } from '@/composables/useNLAccelerator';
import { formatTodoStatus, todoStatusTone } from '@/lib/statusLabels';
import { canReviewRequests } from '@/lib/requestFlowRoles';

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
const role = getProductRole();
const isReviewer = computed(() => canReviewRequests(role.value));

const requestStatusById = computed(() => {
  const map = new Map<string, string>();
  for (const r of requests.value) {
    const it = r as Record<string, unknown>;
    map.set(String(it.id ?? ''), String(it.status ?? ''));
  }
  return map;
});

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

const pendingApprovalItems = computed(() => {
  const pendingKeys = new Set(['pending', 'need-fix', 'supplementing', 'pending_review', 'in_review']);
  return approvals.value
    .map((a) => {
      const it = a as Record<string, unknown>;
      const id = String(it.id ?? '');
      const status = requestStatusById.value.get(id) ?? '';
      const req = requests.value.find((r) => String((r as Record<string, unknown>).id ?? '') === id) as
        | Record<string, unknown>
        | undefined;
      return {
        id,
        suggestion: String(it.suggestion ?? '待审'),
        status,
        resource: String(req?.resourceName ?? '—'),
      };
    })
    .filter((row) => {
      const key = row.status.trim().toLowerCase();
      if (pendingKeys.has(key)) return true;
      return /待|补|审/.test(formatTodoStatus(row.status));
    });
});

const headerMeta = computed(() => {
  if (source.value !== 'live') return '正在加载……';
  if (isReviewer.value) {
    const n = pendingApprovalItems.value.length;
    return n ? `${n} 条待我审批` : '暂无待审申请';
  }
  const n = items.value.length;
  return n ? `${n} 条在途` : '暂无在途申请，可从资源发现发起';
});

const pageTitle = computed(() => (isReviewer.value ? '待我审批' : '在途申请'));

function viewRequest(id: string) {
  window.location.hash = `#/request-flow/request/${id}`;
}
async function quickResubmit(id: string) {
  const status = requestStatusById.value.get(id) ?? '';
  if (status !== 'need-fix') {
    pushToast({
      kind: 'info',
      title: '暂不可重新提交',
      detail:
        status === 'pending'
          ? '申请仍在审批中；若需补件请等待审批人「退回补正」后再操作。'
          : '当前状态不支持重新提交。',
    });
    return;
  }
  await invokeActionStub({
    skillId: 'request.submit',
    payload: { request_id: id },
    successTitle: '已重新提交',
  });
}
</script>

<template>
  <main class="focus-page">
    <section class="panel">
      <PageFocusHeader
        :title="pageTitle"
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

      <template v-if="isReviewer">
        <table v-if="source === 'live' && pendingApprovalItems.length" class="focus-table">
          <thead>
            <tr><th>申请编号</th><th>资源</th><th>状态</th><th>审批建议</th><th>操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="it in pendingApprovalItems" :key="it.id">
              <td><code>{{ it.id }}</code></td>
              <td>{{ it.resource || '—' }}</td>
              <td>
                <span class="status-pill" :class="todoStatusTone(it.status)">{{ formatTodoStatus(it.status) }}</span>
              </td>
              <td>{{ it.suggestion }}</td>
              <td class="table-actions">
                <a :href="`#/request-flow/review/${it.id}`" class="row-link">去审批</a>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-else-if="source === 'live'" class="focus-empty">暂无待审申请。</p>
        <p v-else class="focus-empty">等待数据装载……</p>
      </template>

      <template v-else>
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
                  <button type="button" class="gov-btn gov-btn-secondary" @click="viewRequest(it.id)">查看</button>
                  <button
                    v-if="it.status === 'need-fix'"
                    type="button"
                    class="gov-btn gov-btn-primary"
                    @click="quickResubmit(it.id)"
                  >
                    重新提交
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-else-if="source === 'live'" class="focus-empty">暂无在途申请。</p>
        <p v-else class="focus-empty">等待数据装载……</p>
      </template>
    </section>
  </main>
</template>

<style scoped>
.gov-btn { padding: 4px 10px; border-radius: 6px; font-size: 12px; cursor: pointer; border: 1px solid transparent; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
.gov-btn-secondary { background: #fff; border-color: var(--b-border, #d4e2f4); }
.row-link { color: var(--b-primary, #006be6); font-size: 13px; text-decoration: none; font-weight: 500; }
.row-link:hover { text-decoration: underline; }
</style>
