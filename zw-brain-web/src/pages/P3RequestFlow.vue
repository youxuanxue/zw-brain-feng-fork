<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import { useRequests, useApprovals, useSnapshot, useWebUiConfig } from '@/composables/useSnapshot';
import { invokeActionStub, pushToast } from '@/composables/useActionStub';
import { getProductRole } from '@/composables/useProductRole';
import NLAcceleratorPanel from '@/components/NLAcceleratorPanel.vue';
import type { StructuredAction } from '@/composables/useNLAccelerator';
import { formatTodoStatus, todoStatusTone } from '@/lib/statusLabels';
import { canReviewRequests, canPlatformReviewRequests, canViewNationalChannel } from '@/lib/requestFlowRoles';
import { shortId } from '@/lib/userLanguage';
import { myRequests, myGrants } from '@/lib/roleProjection';
import { filterByRouteAccess } from '@/lib/pageAccess';

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
const { source, data: snapshot } = useSnapshot();
const role = getProductRole();

// 缺陷 1（业务方试用反馈）：一锅炖拆成三个清晰视图——一个视图只回答一个问题。
//   我的申请：我作为需方发起的（草稿/在途/已办结）
//   待我办理：按我的角色码该我处理的（审核/审批/受理）—— 无权角色此 tab 完全不渲染
//   我的授权：我已获得的授权与凭据状态
const isReviewer = computed(() => canReviewRequests(role.value));
const isPlatformReviewer = computed(() => canPlatformReviewRequests(role.value));
// 业务运营员退申请人身份——只保留受理工作台，隐去「我的申请」「我的授权」与申请人快捷链
// （无权=不可见）。业务运营员=受理岗（isPlatformReviewer），非申请人/被授权方。
const isApplicantRole = computed(() => !isPlatformReviewer.value);
// 「待我办理」对位（受理/审核两级）：业务运营员=受理队列（第一级，submitted）；
// 部门管理员=部门审核队列（第二级，dept_approved 受理后）。两者皆无 → tab 不渲染。
const hasTodoQueue = computed(() => isReviewer.value || isPlatformReviewer.value);

// 三视图卡（projection 单源；用途经 dataQuality 降级、来源诚实标识透传）。
const mineCards = computed(() => myRequests(snapshot.value));
const grantCards = computed(() => myGrants(snapshot.value));

type ViewTab = 'mine' | 'todo' | 'grants' | 'national';
// 业务运营员（受理岗）落「待我办理」（受理队列），其余角色落「我的申请」。
const activeView = ref<ViewTab>(isApplicantRole.value ? 'mine' : 'todo');
// 角色切换后若当前 tab 已不该出现，回落到该角色的默认视图：
//   - 受理岗（业务运营员）无「我的申请/我的授权」→ 落「待我办理」；
//   - 申请人角色无「待我办理/国家通道」→ 落「我的申请」。
watch([hasTodoQueue, isApplicantRole], () => {
  if (!isApplicantRole.value && (activeView.value === 'mine' || activeView.value === 'grants')) {
    activeView.value = 'todo';
  }
  if (!hasTodoQueue.value && activeView.value === 'todo') activeView.value = 'mine';
});

// ── 国家直达转报：「国家通道」队列仅业务运营员可见 ∧ flag 门 ──────────
const webui = useWebUiConfig();
const nationalChannel = computed(
  () => (webui.value.nationalChannel as Record<string, unknown> | undefined) ?? {},
);
const nationalChannelEnabled = computed(() => nationalChannel.value.enabled === true);
const nationalProvisioned = computed(() => nationalChannel.value.provisioned === true);
const nationalNotice = computed(() => String(nationalChannel.value.notice ?? '国家通道待配置接入信息'));
const showNationalTab = computed(() => canViewNationalChannel(role.value) && nationalChannelEnabled.value);
watch(showNationalTab, (show) => {
  if (!show && activeView.value === 'national') activeView.value = 'mine';
});

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

// 待我办理（部门管理员）：第二级部门审核队列 = 有条件共享受理后（dept_approved）。
// 无条件共享业务运营员受理即终、不进本级，故本队列只收 dept_approved。
const pendingApprovalItems = computed(() => {
  return approvals.value
    .map((a) => {
      const it = a as Record<string, unknown>;
      const id = String(it.id ?? '');
      const status = requestStatusById.value.get(id) ?? '';
      const req = requests.value.find((r) => String((r as Record<string, unknown>).id ?? '') === id) as
        | Record<string, unknown>
        | undefined;
      return { id, suggestion: String(it.suggestion ?? '待审核'), status, resource: String(req?.resourceName ?? '—') };
    })
    .filter((row) => row.status.trim().toLowerCase() === 'dept_approved');
});

// 待我办理（业务运营员）：第一级受理队列 = 待受理 submitted 单据（无条件受理即终、
// 有条件受理后转部门审核）。受理是申请进入平台后的第一道初级审核。
const platformReviewItems = computed(() => {
  const acceptKeys = new Set(['submitted', 'pending', 'need-fix', 'supplementing', 'pending_review', 'in_review']);
  return approvals.value
    .map((a) => {
      const it = a as Record<string, unknown>;
      const id = String(it.id ?? '');
      const status = requestStatusById.value.get(id) ?? '';
      const req = requests.value.find((r) => String((r as Record<string, unknown>).id ?? '') === id) as
        | Record<string, unknown>
        | undefined;
      return { id, suggestion: String(it.suggestion ?? '待受理'), status, resource: String(req?.resourceName ?? '—') };
    })
    .filter((row) => {
      const key = row.status.trim().toLowerCase();
      if (acceptKeys.has(key)) return true;
      return /待|补|受理/.test(formatTodoStatus(row.status));
    });
});

// 国家通道「待转报」队列（C9）：national ∩ dept_approved。
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
    .filter((row) => row.channelClass === 'national' && row.status.trim().toLowerCase() === 'dept_approved');
});

const todoQueueCount = computed(() =>
  isPlatformReviewer.value ? platformReviewItems.value.length : pendingApprovalItems.value.length,
);

const headerMeta = computed(() => {
  if (source.value !== 'live') return '正在加载……';
  if (activeView.value === 'todo') {
    return todoQueueCount.value ? `${todoQueueCount.value} 条待我办理` : '暂无待我办理的事项';
  }
  if (activeView.value === 'grants') {
    return grantCards.value.length ? `${grantCards.value.length} 项授权` : '暂无已获得的授权';
  }
  return mineCards.value.length ? `${mineCards.value.length} 条我的申请` : '暂无申请，可从资源发现发起';
});

// 页头快捷链（P20：统一过 filterByRouteAccess，无权深链不渲染；P7：资源发现/我的异议/登记需求
// 是申请人侧入口，受理岗不渲染）。交付回执对受理岗也由路由权限自然过滤掉。
const headerLinks = computed(() => {
  const applicantLinks = [
    { label: '资源发现', href: '#/discovery' },
    { label: '交付回执', href: '#/delivery-exchange' },
    { label: '我的异议', href: '#/request-flow/objection' },
    { label: '登记需求', href: '#/request-flow/supply-demand' },
  ];
  const links = isApplicantRole.value
    ? applicantLinks
    : applicantLinks.filter((l) => l.href === '#/delivery-exchange');
  return filterByRouteAccess(links, (l) => l.href, role.value);
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
  await invokeActionStub({ skillId: 'request.submit', payload: { request_id: id }, successTitle: '已重新提交' });
}

// 草稿单一键提交（0605#8）：draft → pending（后端 request.submit 接 draft，提交才启动审批）。
async function quickSubmitDraft(id: string) {
  await invokeActionStub({ skillId: 'request.submit', payload: { request_id: id }, successTitle: '申请已提交，进入审批' });
}
</script>

<template>
  <main class="focus-page">
    <section class="panel">
      <PageFocusHeader
        title="办共享申请"
        :meta="headerMeta"
        :links="headerLinks"
      >
        <template #aside>
          <NLAcceleratorPanel page-anchor="P3" :presets="NL_PRESETS_P3" @action="consumeNLAction" />
        </template>
      </PageFocusHeader>

      <!-- 三视图分栏：一个视图只回答一个问题（缺陷 1）。待我办理无权角色不渲染。
           受理岗（业务运营员）退申请人身份——「我的申请」「我的授权」不渲染。 -->
      <nav class="view-tabs" aria-label="申请视图">
        <button
          v-if="isApplicantRole"
          type="button" class="view-tab" :class="{ active: activeView === 'mine' }"
          data-testid="p3-view-mine" @click="activeView = 'mine'"
        >我的申请</button>
        <button
          v-if="hasTodoQueue"
          type="button" class="view-tab" :class="{ active: activeView === 'todo' }"
          data-testid="p3-view-todo" @click="activeView = 'todo'"
        >待我办理</button>
        <button
          v-if="isApplicantRole"
          type="button" class="view-tab" :class="{ active: activeView === 'grants' }"
          data-testid="p3-view-grants" @click="activeView = 'grants'"
        >我的授权</button>
        <!-- 国家通道：仅业务运营员 ∧ flag-on 渲染（无权/未开=不渲染，承「无权=不可见」）。 -->
        <button
          v-if="showNationalTab"
          type="button" class="view-tab" :class="{ active: activeView === 'national' }"
          data-testid="p3-tab-national" @click="activeView = 'national'"
        >国家通道</button>
      </nav>

      <!-- ── 视图 1：我的申请（需方发起，草稿/在途/已办结）─────────────────── -->
      <div v-show="activeView === 'mine'" data-testid="p3-pane-mine">
        <table v-if="source === 'live' && mineCards.length" class="focus-table">
          <thead>
            <tr><th>编号</th><th>资源</th><th>用途</th><th>状态</th><th>来源</th><th>提交时间</th><th>操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="it in mineCards" :key="it.id">
              <td><a :href="`#/request-flow/request/${it.id}`"><code>{{ shortId(it.id) }}</code></a></td>
              <td>{{ it.resource || '—' }}</td>
              <td>
                <span :class="{ 'purpose-dirty': it.purposeDirty }">{{ it.purpose || '—' }}</span>
              </td>
              <td><span class="status-pill" :class="todoStatusTone(it.status)">{{ formatTodoStatus(it.status) }}</span></td>
              <td>
                <span v-if="it.isLegacyImport" class="origin-chip" title="来自旧平台历史导入">历史导入</span>
                <span v-else class="origin-chip origin-chip--live">在产</span>
              </td>
              <td>{{ it.submittedAt || '—' }}</td>
              <td class="table-actions">
                <div class="table-actions-inner">
                  <button type="button" class="gov-btn gov-btn-secondary" @click="viewRequest(it.id)">查看</button>
                  <button v-if="it.status === 'draft'" type="button" class="gov-btn gov-btn-primary" data-testid="quick-submit-draft" @click="quickSubmitDraft(it.id)">提交申请</button>
                  <button v-if="it.status === 'need-fix'" type="button" class="gov-btn gov-btn-primary" @click="quickResubmit(it.id)">重新提交</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-else-if="source === 'live'" class="focus-empty">暂无申请。可从「资源发现」找到数据后发起共享申请。</p>
        <p v-else class="focus-empty">等待数据装载……</p>
      </div>

      <!-- ── 视图 2：待我办理（受理 / 部门审核 两级）──────────────── -->
      <div v-if="hasTodoQueue" v-show="activeView === 'todo'" data-testid="p3-pane-todo">
        <template v-if="isPlatformReviewer">
          <table v-if="source === 'live' && platformReviewItems.length" class="focus-table">
            <thead><tr><th>申请编号</th><th>资源</th><th>状态</th><th>受理建议</th><th>操作</th></tr></thead>
            <tbody>
              <tr v-for="it in platformReviewItems" :key="it.id">
                <td><code>{{ shortId(it.id) }}</code></td>
                <td>{{ it.resource || '—' }}</td>
                <td><span class="status-pill" :class="todoStatusTone(it.status)">{{ formatTodoStatus(it.status) }}</span></td>
                <td>{{ it.suggestion }}</td>
                <td class="table-actions"><a :href="`#/request-flow/review/${it.id}`" class="row-link">去受理</a></td>
              </tr>
            </tbody>
          </table>
          <p v-else-if="source === 'live'" class="focus-empty">暂无待受理的申请。</p>
          <p v-else class="focus-empty">等待数据装载……</p>
        </template>
        <template v-else-if="isReviewer">
          <table v-if="source === 'live' && pendingApprovalItems.length" class="focus-table">
            <thead><tr><th>申请编号</th><th>资源</th><th>状态</th><th>审核建议</th><th>操作</th></tr></thead>
            <tbody>
              <tr v-for="it in pendingApprovalItems" :key="it.id">
                <td><code>{{ shortId(it.id) }}</code></td>
                <td>{{ it.resource || '—' }}</td>
                <td><span class="status-pill" :class="todoStatusTone(it.status)">{{ formatTodoStatus(it.status) }}</span></td>
                <td>{{ it.suggestion }}</td>
                <td class="table-actions"><a :href="`#/request-flow/review/${it.id}`" class="row-link">去审核</a></td>
              </tr>
            </tbody>
          </table>
          <p v-else-if="source === 'live'" class="focus-empty">暂无待部门审核的申请。</p>
          <p v-else class="focus-empty">等待数据装载……</p>
        </template>
      </div>

      <!-- ── 视图：国家通道独立 tab，仅业务运营员 ∧ flag-on 渲染 ──────── -->
      <div v-if="showNationalTab" v-show="activeView === 'national'" class="national-pane" data-testid="p3-national-pane">
        <p class="national-notice" :class="{ pending: !nationalProvisioned }">{{ nationalNotice }}</p>
        <table v-if="source === 'live' && nationalEscalateItems.length" class="focus-table">
          <thead><tr><th>申请编号</th><th>资源</th><th>用途</th><th>国家通道</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-for="it in nationalEscalateItems" :key="it.id">
              <td><code>{{ shortId(it.id) }}</code></td>
              <td>{{ it.resource || '—' }}</td>
              <td>{{ it.purpose || '—' }}</td>
              <td>
                <span v-if="escalateStageById[it.id]" class="status-pill warn">{{ escalateStageById[it.id] }}</span>
                <span v-else class="muted">待转报</span>
              </td>
              <td class="table-actions">
                <button type="button" class="gov-btn gov-btn-primary" data-testid="p3-escalate-btn" @click="escalateToNational(it.id)">审核通过 + 转报国家平台</button>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-else-if="source === 'live'" class="focus-empty">暂无待转报的国家级申请。</p>
        <p v-else class="focus-empty">等待数据装载……</p>
      </div>

      <!-- ── 视图 3：我的授权（已获得的授权与凭据状态）─────────────────────── -->
      <div v-show="activeView === 'grants'" data-testid="p3-pane-grants">
        <table v-if="source === 'live' && grantCards.length" class="focus-table">
          <thead><tr><th>编号</th><th>资源</th><th>授权状态</th><th>来源</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-for="it in grantCards" :key="it.id">
              <td><a :href="`#/request-flow/request/${it.id}`"><code>{{ shortId(it.id) }}</code></a></td>
              <td>{{ it.resource || '—' }}</td>
              <td><span class="status-pill" :class="todoStatusTone(it.status)">{{ formatTodoStatus(it.status) }}</span></td>
              <td>
                <span v-if="it.isLegacyImport" class="origin-chip" title="来自旧平台历史导入">历史导入</span>
                <span v-else class="origin-chip origin-chip--live">在产</span>
              </td>
              <td class="table-actions"><button type="button" class="gov-btn gov-btn-secondary" @click="viewRequest(it.id)">查看凭据</button></td>
            </tr>
          </tbody>
        </table>
        <p v-else-if="source === 'live'" class="focus-empty">暂无已获得的授权。共享申请通过后，授权与凭据将在此显示。</p>
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
.view-tabs { display: flex; gap: 6px; margin: 4px 0 16px; border-bottom: 1px solid var(--b-border, #d4e2f4); }
.view-tab { background: none; border: 0; border-bottom: 2px solid transparent; padding: 8px 16px; cursor: pointer; font-size: 14px; font-weight: 500; color: var(--b-muted, #5c6370); }
.view-tab.active { color: var(--b-primary, #006be6); border-bottom-color: var(--b-primary, #006be6); font-weight: 600; }
.sub-title { font-size: 14px; font-weight: 600; margin: 18px 0 8px; color: var(--b-neutral-text, #1a1d21); }
.national-notice { font-size: 13px; padding: 8px 12px; border-radius: 6px; background: #eef4fb; color: var(--b-primary, #006be6); margin: 0 0 12px; }
.national-notice.pending { background: #fff7e0; color: #8a6d00; }
.status-pill.warn { background: #fff7e0; color: #8a6d00; }
.muted { color: var(--b-muted, #9aa0a6); font-size: 12px; }
/* 缺陷 3：脏值降级次要样式（用途列「测试」「167」不裸奔，降级为灰「未填写用途」）。 */
.purpose-dirty { color: var(--b-muted, #9aa0a6); font-style: italic; font-size: 13px; }
/* 缺陷 3：来源克制区分——历史导入单淡灰、在产单淡蓝。 */
.origin-chip { display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 11px; background: #eef0f3; color: #6b7280; }
.origin-chip--live { background: #e8f2fc; color: var(--b-primary, #006be6); }
</style>
