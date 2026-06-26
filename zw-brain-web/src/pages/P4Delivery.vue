<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import { useDeliveryTasks, useSnapshot } from '@/composables/useSnapshot';
import { getProductRole } from '@/composables/useProductRole';
import { downloadDeliveryFile } from '@/composables/useDeliveryDownload';
import { invokeActionStub, pushToast } from '@/composables/useActionStub';
import { formatTodoStatus, todoStatusTone } from '@/lib/statusLabels';
import { deriveRecordName, formatChannel, formatTime, shortId } from '@/lib/userLanguage';
import { myRequests, myGrants } from '@/lib/roleProjection';
import { canPlatformReviewRequests } from '@/lib/requestFlowRoles';
import { filterByRouteAccess } from '@/lib/pageAccess';

// 「办申请」导航解体（IA 重构）：消费方「我的数据」一站式入口收口到领数据——
//   我的申请 (mine)   ：我作为需方发起的（草稿 / 在途 / 已办结），深链申请详情
//   我的授权 (grants) ：我已获得的授权与凭据状态
//   交付任务 (tasks)  ：审批通过后的数据交付（查看授权 / 下载 / 交换任务）
// 受理 / 审核已迁工作台，本页不承接 reviewer 待办。

const tasks = useDeliveryTasks();
const { source, data: snapshot } = useSnapshot();
const role = getProductRole();

// 申请人身份判定：受理岗（业务运营员）退申请人身份——「我的申请」「我的授权」不渲染
// （无权 = 不可见）。delivery shell 角色集本就只含操作员 + 管理员（皆申请人），此处为纵深防御。
const isApplicantRole = computed(() => !canPlatformReviewRequests(role.value));

// 我的申请 / 我的授权（projection 单源；用途经 dataQuality 降级、来源诚实标识透传）。
const mineCards = computed(() => myRequests(snapshot.value));
const grantCards = computed(() => myGrants(snapshot.value));

// 交付任务（原 P4Delivery 内容，按资源类型分流操作）。
const taskItems = computed(() =>
  tasks.value.map((t) => {
    const it = t as Record<string, unknown>;
    const status = String(it.status ?? '');
    const id = String(it.id ?? '');
    return {
      id,
      idShort: shortId(id),
      // 名缺失 / 名本身是裸 hex → 派生「交付任务 …末6位」，不裸出 32 位 hex 主文本。
      name: deriveRecordName(it.name, id, '交付任务'),
      requestId: String(it.requestId ?? ''),
      channel: formatChannel(it.channel),
      status,
      statusLabel: formatTodoStatus(status),
      updatedAt: formatTime(it.updatedAt),
      // 交付资源类型（table/file/api），驱动操作按钮分流（API=查看授权、文件=下载、库表=交换任务）。
      resourceKind: String(it.resourceKind ?? ''),
    };
  }),
);

type DeliveryTab = 'mine' | 'grants' | 'tasks';
// 申请人默认落「我的申请」；非申请人（纵深防御）落「交付任务」。
const activeTab = ref<DeliveryTab>(isApplicantRole.value ? 'mine' : 'tasks');
// 角色切换后若当前 tab 已不该出现（非申请人停在 mine/grants）→ 回落交付任务。
watch(isApplicantRole, (applicant) => {
  if (!applicant && (activeTab.value === 'mine' || activeTab.value === 'grants')) {
    activeTab.value = 'tasks';
  }
});

const headerMeta = computed(() => {
  if (source.value !== 'live') return '正在加载……';
  if (activeTab.value === 'mine') {
    return mineCards.value.length ? `${mineCards.value.length} 条申请 · 下一步在每行右侧` : '暂无申请 · 可从「找数据」发起';
  }
  if (activeTab.value === 'grants') {
    return grantCards.value.length ? `${grantCards.value.length} 项授权 · 查看凭据和授权状态` : '暂无授权 · 申请通过后在此领取';
  }
  return taskItems.value.length ? `${taskItems.value.length} 条任务 · 领取、下载、核对在此完成` : '暂无任务 · 审批通过后会出现在此';
});

const visibleSteps = computed(() => [
  {
    key: 'mine',
    label: '申请进度',
    count: mineCards.value.length,
    active: activeTab.value === 'mine',
    available: isApplicantRole.value,
  },
  {
    key: 'grants',
    label: '授权凭据',
    count: grantCards.value.length,
    active: activeTab.value === 'grants',
    available: isApplicantRole.value,
  },
  {
    key: 'tasks',
    label: '交付任务',
    count: taskItems.value.length,
    active: activeTab.value === 'tasks',
    available: true,
  },
].filter((step) => step.available));

// 页头快捷链（统一过 filterByRouteAccess，无权深链不渲染）。提异议 / 审计回放为消费方入口。
const headerLinks = computed(() =>
  filterByRouteAccess(
    [
      { label: '提异议', href: '#/request-flow/objection/new' },
      { label: '审计回放', href: '#/compliance-ops' },
    ],
    (l) => l.href,
    role.value,
  ),
);

function viewRequest(id: string) {
  window.location.hash = `#/request-flow/request/${id}`;
}
function openCredential(reqId: string) {
  if (reqId) window.location.hash = `#/delivery-exchange/credential/${reqId}`;
}
function openTask(id: string) {
  if (id) window.location.hash = `#/delivery-exchange/task/${id}`;
}

// 草稿单一键提交：draft → pending（后端 request.submit 接 draft，提交才启动审批）。
async function quickSubmitDraft(id: string) {
  await invokeActionStub({ skillId: 'request.submit', payload: { request_id: id }, successTitle: '申请已提交，进入审批' });
}
async function quickResubmit(id: string) {
  const card = mineCards.value.find((c) => c.id === id);
  if (!card || card.status !== 'need-fix') {
    pushToast({ kind: 'info', title: '暂不可重新提交', detail: '当前状态不支持重新提交。' });
    return;
  }
  await invokeActionStub({ skillId: 'request.submit', payload: { request_id: id }, successTitle: '已重新提交' });
}
</script>

<template>
  <main class="focus-page">
    <section class="panel">
      <PageFocusHeader title="领数据" :meta="headerMeta" :links="headerLinks" />

      <ol class="delivery-steps" aria-label="领数据进度">
        <li
          v-for="step in visibleSteps"
          :key="step.key"
          class="delivery-step"
          :class="{ active: step.active }"
        >
          <span>{{ step.label }}</span>
          <strong>{{ step.count }}</strong>
        </li>
      </ol>

      <!-- 三视图分栏：一个视图只回答一个问题。我的申请 / 我的授权对非申请人不渲染（无权 = 不可见）。 -->
      <nav class="view-tabs" aria-label="领数据视图">
        <button
          v-if="isApplicantRole"
          type="button" class="view-tab" :class="{ active: activeTab === 'mine' }"
          data-testid="p4-view-mine" @click="activeTab = 'mine'"
        >我的申请</button>
        <button
          v-if="isApplicantRole"
          type="button" class="view-tab" :class="{ active: activeTab === 'grants' }"
          data-testid="p4-view-grants" @click="activeTab = 'grants'"
        >我的授权</button>
        <button
          type="button" class="view-tab" :class="{ active: activeTab === 'tasks' }"
          data-testid="p4-view-tasks" @click="activeTab = 'tasks'"
        >交付任务</button>
      </nav>

      <!-- ── 视图 1：我的申请（需方发起，草稿 / 在途 / 已办结）──────────────── -->
      <div v-if="isApplicantRole" v-show="activeTab === 'mine'" data-testid="p4-pane-mine">
        <table v-if="source === 'live' && mineCards.length" class="focus-table">
          <thead>
            <tr><th>编号</th><th>资源</th><th>用途</th><th>状态</th><th>来源</th><th>提交时间</th><th>操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="it in mineCards" :key="it.id">
              <td><a :href="`#/request-flow/request/${it.id}`" data-testid="p4-mine-deeplink"><code>{{ shortId(it.id) }}</code></a></td>
              <td>{{ it.resource || '—' }}</td>
              <td><span :class="{ 'purpose-dirty': it.purposeDirty }">{{ it.purpose || '—' }}</span></td>
              <td><span class="status-pill" :class="todoStatusTone(it.status)">{{ formatTodoStatus(it.status) }}</span></td>
              <td>
                <span v-if="it.isLegacyImport" class="origin-chip" title="来自旧平台历史导入">历史导入</span>
                <span v-else class="origin-chip origin-chip--live">在产</span>
              </td>
              <td>{{ it.submittedAt || '—' }}</td>
              <td class="table-actions">
                <div class="table-actions-inner">
                  <button v-if="it.status === 'draft'" type="button" class="gov-btn gov-btn-primary" data-testid="quick-submit-draft" @click="quickSubmitDraft(it.id)">提交申请</button>
                  <button v-else-if="it.status === 'need-fix'" type="button" class="gov-btn gov-btn-primary" @click="quickResubmit(it.id)">重新提交</button>
                  <button v-else type="button" class="gov-btn gov-btn-secondary" @click="viewRequest(it.id)">查看进度</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-else-if="source === 'live'" class="focus-empty">暂无申请。可从「找数据」找到资源后发起共享申请。</p>
        <p v-else class="focus-empty">等待数据装载……</p>
      </div>

      <!-- ── 视图 2：我的授权（已获得的授权与凭据状态）────────────────────── -->
      <div v-if="isApplicantRole" v-show="activeTab === 'grants'" data-testid="p4-pane-grants">
        <table v-if="source === 'live' && grantCards.length" class="focus-table">
          <thead><tr><th>编号</th><th>资源</th><th>授权状态</th><th>来源</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-for="it in grantCards" :key="it.id">
              <td><a :href="`#/request-flow/request/${it.id}`" data-testid="p4-grant-deeplink"><code>{{ shortId(it.id) }}</code></a></td>
              <td>{{ it.resource || '—' }}</td>
              <td><span class="status-pill" :class="todoStatusTone(it.status)">{{ formatTodoStatus(it.status) }}</span></td>
              <td>
                <span v-if="it.isLegacyImport" class="origin-chip" title="来自旧平台历史导入">历史导入</span>
                <span v-else class="origin-chip origin-chip--live">在产</span>
              </td>
              <td class="table-actions"><button type="button" class="gov-btn gov-btn-primary" @click="openCredential(it.id)">领取凭据</button></td>
            </tr>
          </tbody>
        </table>
        <p v-else-if="source === 'live'" class="focus-empty">暂无已获得的授权。共享申请通过后，授权与凭据将在此显示。</p>
        <p v-else class="focus-empty">等待数据装载……</p>
      </div>

      <!-- ── 视图 3：交付任务（按资源类型分流操作）──────────────────────── -->
      <div v-show="activeTab === 'tasks'" data-testid="p4-pane-tasks">
        <table v-if="source === 'live' && taskItems.length" class="focus-table">
          <thead>
            <tr><th>编号</th><th>名称</th><th>渠道</th><th>状态</th><th>更新</th><th>操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="t in taskItems" :key="t.id">
              <td><a :href="`#/delivery-exchange/task/${t.id}`"><code>{{ t.idShort }}</code></a></td>
              <td>{{ t.name }}</td>
              <td>{{ t.channel }}</td>
              <td><span class="status-pill" :class="todoStatusTone(t.status)">{{ t.statusLabel }}</span></td>
              <td>{{ t.updatedAt }}</td>
              <td class="table-actions">
                <div class="table-actions-inner">
                  <!-- 按资源类型分流（0611 业务口径确认单 §B，方案 B 终裁）：
                       API=「查看授权」（网关 appkey/secret）、文件=「下载」（受控下载请求 + 下载日志）、
                       库表=「交换任务」单一入口（点进任务详情查看送达进度、核对交换结果）；
                       类型推不出时回落「查看授权」（与凭据页通用授权呈现同源）。 -->
                  <button
                    v-if="t.resourceKind === 'file'"
                    type="button"
                    class="gov-btn gov-btn-primary"
                    @click="downloadDeliveryFile(t.id, t.name)"
                  >
                    下载
                  </button>
                  <button
                    v-else-if="t.resourceKind === 'table'"
                    type="button"
                    class="gov-btn gov-btn-primary"
                    @click="openTask(t.id)"
                  >
                    交换任务
                  </button>
                  <button v-else type="button" class="gov-btn gov-btn-secondary" @click="openCredential(t.requestId)">
                    查看授权
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-else-if="source === 'live'" class="focus-empty">暂无交付任务。申请通过并生成交付后，这里会出现领取、下载或核对动作。</p>
        <p v-else class="focus-empty">等待数据装载……</p>
      </div>
    </section>
  </main>
</template>

<style scoped>
.delivery-steps {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 8px;
  margin: 8px 0 16px;
  padding: 0;
  list-style: none;
}
.delivery-step {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  min-height: 44px;
  padding: 8px 12px;
  border: 1px solid var(--b-border, #d4e2f4);
  border-radius: 6px;
  background: #fff;
  color: var(--b-muted, #5c6370);
  font-size: 13px;
  line-height: 1.4;
}
.delivery-step.active {
  border-color: var(--b-primary, #006be6);
  background: #f2f7ff;
  color: var(--b-neutral-text, #1a1d21);
}
.delivery-step strong {
  font-size: 18px;
  line-height: 1;
  color: var(--b-primary, #006be6);
}
.view-tabs { display: flex; gap: 6px; margin: 4px 0 16px; border-bottom: 1px solid var(--b-border, #d4e2f4); }
.view-tab { background: none; border: 0; border-bottom: 2px solid transparent; padding: 8px 16px; cursor: pointer; font-size: 14px; font-weight: 500; color: var(--b-muted, #5c6370); }
.view-tab.active { color: var(--b-primary, #006be6); border-bottom-color: var(--b-primary, #006be6); font-weight: 600; }
.gov-btn { padding: 4px 10px; border-radius: 6px; font-size: 12px; cursor: pointer; border: 1px solid transparent; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
.gov-btn-secondary { background: #fff; border-color: var(--b-border, #d4e2f4); }
/* 用途脏值降级次要样式（用途列裸值不裸奔，降级为灰斜体）。 */
.purpose-dirty { color: var(--b-muted, #9aa0a6); font-style: italic; font-size: 13px; }
/* 来源克制区分——历史导入单淡灰、在产单淡蓝。 */
.origin-chip { display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 11px; background: #eef0f3; color: #6b7280; }
.origin-chip--live { background: #e8f2fc; color: var(--b-primary, #006be6); }
</style>
