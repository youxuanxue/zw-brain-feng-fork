<script setup lang="ts">
import { computed, ref } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import { useRequests, useApprovals, useSnapshot, useWebUiConfig } from '@/composables/useSnapshot';
import { invokeActionStub, pushToast } from '@/composables/useActionStub';
import { getProductRole } from '@/composables/useProductRole';
import NLAcceleratorPanel from '@/components/NLAcceleratorPanel.vue';
import type { StructuredAction } from '@/composables/useNLAccelerator';
import { formatTodoStatus, todoStatusTone } from '@/lib/statusLabels';
import { canReviewRequests, canPlatformReviewRequests, canViewNationalChannel } from '@/lib/requestFlowRoles';

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
const isPlatformReviewer = computed(() => canPlatformReviewRequests(role.value));

// 国家直达转报：「国家通道」tab 仅 BUSIAUDIT 可见 ∧ flag 门
// （snapshot.webui.nationalChannel.enabled）。两者任一不满足 → tab 入口完全不渲染（承「无权=不可见」）。
const webui = useWebUiConfig();
const nationalChannel = computed(
  () => (webui.value.nationalChannel as Record<string, unknown> | undefined) ?? {},
);
const nationalChannelEnabled = computed(() => nationalChannel.value.enabled === true);
const nationalProvisioned = computed(() => nationalChannel.value.provisioned === true);
const nationalNotice = computed(() => String(nationalChannel.value.notice ?? '国家通道待配置接入信息'));
const showNationalTab = computed(() => canViewNationalChannel(role.value) && nationalChannelEnabled.value);
const activeTab = ref<'main' | 'national'>('main');

// 转报后就地显示计算态 overlay（不污染主 status；后端不持久化主状态，本期诚实「待回执」）。
const escalateStageById = ref<Record<string, string>>({});

async function escalateToNational(id: string) {
  const result = await invokeActionStub({
    skillId: 'application.escalate_national',
    payload: { application_code: id, action: 'escalate' },
    successTitle: '已转报国家平台，待回执',
  });
  if (!result.ok) return;
  const data = (result.data ?? {}) as Record<string, unknown>;
  const inner = (data.result ?? data) as Record<string, unknown>;
  escalateStageById.value = {
    ...escalateStageById.value,
    [id]: String(inner.display_status ?? '国家通道转报中'),
  };
}

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

// J1 有条件共享第二步「平台复核」队列：dept 已同意(dept_approved)、等待省大数据局
// 业务运营员复核的申请。仅 ROLE_BUSIAUDIT 可见（无权限不渲染）。
const platformReviewItems = computed(() => {
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
        suggestion: String(it.suggestion ?? '待复核'),
        status,
        resource: String(req?.resourceName ?? '—'),
      };
    })
    .filter((row) => row.status.trim().toLowerCase() === 'dept_approved');
});

// 国家通道「待转报」队列（C9）：请求国家级数据(channelClass==='national')且已到本级
// 审核通过(dept_approved)、可由业务运营员转报国家平台的申请。**不是** own-items——
// 业务运营员转报的是「别人请求国家级数据」的待办，不是自己在途申请。
//
// 口径 = requests ∩ channelClass==='national' ∩ status==='dept_approved'。直接遍历
// requests（卡片自带 channelClass + status，record→card 透自 payload_json["channel_class"]/
// status），不经 approvals 卡——approvals 由 approval_case 表现算投影，legacy apply 记录
// 通常无对应 approval_case，故待转报队列以 requests 为单一事实源。深层口径/缺口见
// commit landing-note 与 docs/preflight-debt.md C9 条。
const nationalEscalateItems = computed(() => {
  return requests.value
    .map((r) => {
      const it = r as Record<string, unknown>;
      return {
        id: String(it.id ?? ''),
        resource: String(it.resourceName ?? it.resource_id ?? '—'),
        purpose: String(it.purpose ?? it.title ?? '—'),
        status: String(it.status ?? ''),
        channelClass: String(it.channelClass ?? 'internal'),
      };
    })
    .filter(
      (row) =>
        row.channelClass === 'national' && row.status.trim().toLowerCase() === 'dept_approved',
    );
});

const headerMeta = computed(() => {
  if (source.value !== 'live') return '正在加载……';
  if (isPlatformReviewer.value) {
    const n = platformReviewItems.value.length;
    return n ? `${n} 条待平台复核` : '暂无待复核申请';
  }
  if (isReviewer.value) {
    const n = pendingApprovalItems.value.length;
    return n ? `${n} 条待我审批` : '暂无待审申请';
  }
  const n = items.value.length;
  return n ? `${n} 条在途` : '暂无在途申请，可从资源发现发起';
});

const pageTitle = computed(() => {
  if (isPlatformReviewer.value) return '平台复核';
  if (isReviewer.value) return '我作为提供方';
  return '在途申请';
});

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
          { label: '我的异议', href: '#/request-flow/objection' },
          { label: '登记需求', href: '#/request-flow/supply-demand' },
        ]"
      >
        <template #aside>
          <NLAcceleratorPanel page-anchor="P3" :presets="NL_PRESETS_P3" @action="consumeNLAction" />
        </template>
      </PageFocusHeader>

      <nav v-if="showNationalTab" class="channel-tabs" aria-label="申请分类">
        <button
          type="button" class="channel-tab" :class="{ active: activeTab === 'main' }"
          data-testid="p3-tab-main" @click="activeTab = 'main'"
        >主流程</button>
        <button
          type="button" class="channel-tab" :class="{ active: activeTab === 'national' }"
          data-testid="p3-tab-national" @click="activeTab = 'national'"
        >国家通道</button>
      </nav>

      <div v-show="!showNationalTab || activeTab === 'main'">
      <template v-if="isPlatformReviewer">
        <table v-if="source === 'live' && platformReviewItems.length" class="focus-table">
          <thead>
            <tr><th>申请编号</th><th>资源</th><th>状态</th><th>复核建议</th><th>操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="it in platformReviewItems" :key="it.id">
              <td><code>{{ it.id }}</code></td>
              <td>{{ it.resource || '—' }}</td>
              <td>
                <span class="status-pill" :class="todoStatusTone(it.status)">{{ formatTodoStatus(it.status) }}</span>
              </td>
              <td>{{ it.suggestion }}</td>
              <td class="table-actions">
                <a :href="`#/request-flow/review/${it.id}`" class="row-link">去复核</a>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-else-if="source === 'live'" class="focus-empty">暂无待平台复核的申请。</p>
        <p v-else class="focus-empty">等待数据装载……</p>
      </template>

      <template v-else-if="isReviewer">
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
      </div>

      <div v-if="showNationalTab" v-show="activeTab === 'national'" class="national-pane" data-testid="p3-national-pane">
        <p class="national-notice" :class="{ pending: !nationalProvisioned }">{{ nationalNotice }}</p>
        <table v-if="source === 'live' && nationalEscalateItems.length" class="focus-table">
          <thead>
            <tr><th>申请编号</th><th>资源</th><th>用途</th><th>国家通道</th><th>操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="it in nationalEscalateItems" :key="it.id">
              <td><code>{{ it.id }}</code></td>
              <td>{{ it.resource || '—' }}</td>
              <td>{{ it.purpose || '—' }}</td>
              <td>
                <span v-if="escalateStageById[it.id]" class="status-pill warn">{{ escalateStageById[it.id] }}</span>
                <span v-else class="muted">待转报</span>
              </td>
              <td class="table-actions">
                <button
                  type="button" class="gov-btn gov-btn-primary"
                  data-testid="p3-escalate-btn"
                  @click="escalateToNational(it.id)"
                >审核通过 + 转报国家平台</button>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-else-if="source === 'live'" class="focus-empty">暂无待转报的国家级申请。</p>
        <p v-else class="focus-empty">等待数据装载……</p>
      </div>
    </section>
  </main>
</template>

<style scoped>
.gov-btn { padding: 4px 10px; border-radius: 6px; font-size: 12px; cursor: pointer; border: 1px solid transparent; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
.gov-btn-secondary { background: #fff; border-color: var(--b-border, #d4e2f4); }
.row-link { color: var(--b-primary, #006be6); font-size: 13px; text-decoration: none; font-weight: 500; }
.row-link:hover { text-decoration: underline; }
.channel-tabs { display: flex; gap: 6px; margin: 4px 0 12px; border-bottom: 1px solid var(--b-border, #d4e2f4); }
.channel-tab { background: none; border: 0; border-bottom: 2px solid transparent; padding: 6px 14px; cursor: pointer; font-size: 13px; color: var(--b-muted, #5c6370); }
.channel-tab.active { color: var(--b-primary, #006be6); border-bottom-color: var(--b-primary, #006be6); font-weight: 600; }
.national-notice { font-size: 13px; padding: 8px 12px; border-radius: 6px; background: #eef4fb; color: var(--b-primary, #006be6); margin: 0 0 12px; }
.national-notice.pending { background: #fff7e0; color: #8a6d00; }
.status-pill.warn { background: #fff7e0; color: #8a6d00; }
.muted { color: var(--b-muted, #9aa0a6); font-size: 12px; }
</style>
