<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import {
  disableTenantCapability,
  enableTenantCapability,
  reviewPackage,
  rollbackPackage,
  updatePackageTrustLevel,
  useExposureMatrix,
  usePackageList,
} from '@/composables/usePackageLifecycle';
import { useEngineSlots } from '@/composables/useEngineSlots';
import { invokeActionStub, pushToast } from '@/composables/useActionStub';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DataSourceBadge from '@/components/DataSourceBadge.vue';
import NLAcceleratorPanel from '@/components/NLAcceleratorPanel.vue';
import type { StructuredAction } from '@/composables/useNLAccelerator';
import { trustPillClass } from '@/lib/packageDisplay';

// B1.2 接入扩展中心 —— 按「能力来源」组织，全程人话（见 docs/decisions/
// integration-admin-governance-axis-refactor.md）。
//
// 核心心智：同一能力底座，两种来源，两套准入强度。
//   · 平台内置（execution_binding=builtin）：产品自带、默认可信，由研发按能力注册路径扩展。
//   · 外部接入（execution_binding=external_capability）：外来系统经海关审批接入、需信任评估。
// 「5 个外部系统」与「238 项能力」不是一个量纲：238 = 内置 224 + 外部 14；5 = 外部接入的系统数。
//
// 诚实校准（不可 overclaim）：
//   · 外部能力今天只有「审批接入」治理元数据就位；实际运行时调用待 AgentRuntime 执行桥打通
//     （dispatch 仍是静态代码绑定，external_capability manifest 是契约空壳）。UI 不得暗示已可跑。
//   · 「自助新增能力」热更新今天做不到（静态 DISPATCH_TABLE + 段28 三处一致守卫）；
//     内置扩展走研发代码路径，本页只如实说明、不放运行时表单。详见 B 方案
//     docs/decisions/runtime-capability-registration-bridge-proposal.md。
//
// 治理轴：能力总览 / 外部接入 / 身份治理   ｜   配置轴：流程与表单配置
// 仅 ROLE_BUSIAUDIT / ROLE_SYSTEM 可见（productShellNav 角色门 + 路由 beforeEach 守卫）。

type TabKind = 'overview' | 'external' | 'engines';
const activeTab = ref<TabKind>('overview');

const GOV_TABS: { key: TabKind; label: string }[] = [
  { key: 'overview', label: '能力总览' },
  { key: 'external', label: '外部接入' },
];
const CFG_TABS: { key: TabKind; label: string }[] = [{ key: 'engines', label: '流程与表单配置' }];

const NL_PRESETS_B12 = ['未审核能力包', '近 7 天 IAM 失败', '看接入故障'];

const packages = usePackageList();
const matrix = useExposureMatrix();
const { slots } = useEngineSlots();

onMounted(() => {
  void packages.load();
  void matrix.load({});
});

function switchTab(t: TabKind): void {
  activeTab.value = t;
}

async function refreshActive(): Promise<void> {
  if (activeTab.value === 'overview') {
    await Promise.all([packages.load(), matrix.load({})]);
  } else if (activeTab.value === 'external') {
    await packages.load();
  }
}

function consumeNLAction(action: StructuredAction): void {
  if (action.kind === 'invoke' && action.target) {
    void invokeActionStub({
      skillId: action.target,
      payload: action.payload,
      role: 'ROLE_BUSIAUDIT',
      successTitle: action.label,
    });
  } else if (action.kind === 'filter' || action.kind === 'draft') {
    pushToast({ kind: 'info', title: '已应用', detail: action.label });
  }
}

async function onReview(pkgId: string, decision: 'approve' | 'return_for_fix' | 'reject'): Promise<void> {
  const label = decision === 'approve' ? '批准上线' : decision === 'return_for_fix' ? '退回补充' : '驳回';
  if (!window.confirm(`确认对外部系统 ${pkgId} 执行「${label}」？此操作会写审计 + 持久化。`)) return;
  const r = await reviewPackage(pkgId, decision, true);
  if (r.ok) {
    pushToast({ kind: 'ok', title: '已落审计', detail: `${pkgId} · ${label} · audit_id=${r.audit_id ?? '—'}` });
    await packages.load();
  } else {
    pushToast({ kind: 'error', title: '审核失败', detail: r.error ?? '后端报错' });
  }
}

async function onEnable(pkgId: string): Promise<void> {
  if (!window.confirm(`确认启用外部系统 ${pkgId}？启用后此能力可被本租户调用。`)) return;
  const r = await enableTenantCapability(pkgId, true);
  pushToast(r.ok
    ? { kind: 'ok', title: '已启用', detail: pkgId }
    : { kind: 'error', title: '启用失败', detail: r.error ?? '—' });
  if (r.ok) await packages.load();
}

async function onDisable(pkgId: string): Promise<void> {
  if (!window.confirm(`确认停用外部系统 ${pkgId}？停用后本租户调用该能力会被拦下。`)) return;
  const r = await disableTenantCapability(pkgId, true);
  pushToast(r.ok
    ? { kind: 'ok', title: '已停用', detail: pkgId }
    : { kind: 'error', title: '停用失败', detail: r.error ?? '—' });
  if (r.ok) await packages.load();
}

async function onRollback(pkgId: string): Promise<void> {
  const reason = window.prompt(`请说明回滚原因（必填）：\n外部系统 ${pkgId}`);
  if (!reason) return;
  if (!window.confirm(`将外部系统 ${pkgId} 回滚到上一版本？\n原因：${reason}`)) return;
  const r = await rollbackPackage(pkgId, reason, true);
  pushToast(r.ok
    ? { kind: 'ok', title: '已回滚', detail: `${pkgId} · ${String(r.result?.rolled_back_to ?? '—')}` }
    : { kind: 'error', title: '回滚失败', detail: r.error ?? '—' });
  if (r.ok) await packages.load();
}

async function onTrustLevelChange(pkgId: string): Promise<void> {
  const target = window.prompt(
    `升降外部系统 ${pkgId} 的内置信任级，请输入目标级别：\nbaseline / reviewed / restricted / revoked`
  );
  if (!target) return;
  if (!['baseline', 'reviewed', 'restricted', 'revoked'].includes(target)) {
    pushToast({ kind: 'warn', title: '取值非法', detail: '只接受 baseline / reviewed / restricted / revoked' });
    return;
  }
  const reason = window.prompt(`升降级原因（必填）：`);
  if (!reason) return;
  if (!window.confirm(`确认将 ${pkgId} 内置信任级改为「${target}」？此操作会写审计。`)) return;
  const r = await updatePackageTrustLevel(
    pkgId,
    target as 'baseline' | 'reviewed' | 'restricted' | 'revoked',
    reason,
    true
  );
  pushToast(r.ok
    ? { kind: 'ok', title: '信任级已更新', detail: `${pkgId} → ${target}` }
    : { kind: 'error', title: '更新失败', detail: r.error ?? '—' });
  if (r.ok) await packages.load();
}

// ---- 人话标签映射（避免把工程串糊用户脸；R12 段24/24b）----
const SURFACE_LABELS: Record<string, string> = {
  webui: '页面',
  api: '接口',
  cli: '命令行',
  mcp: 'MCP',
  a2a: '智能体互联',
};
const JOURNEY_LABELS: Record<string, string> = {
  j1: '找数·用数',
  j2: '供数·维数',
  b1: '后台支撑',
  infra: '基础设施',
  national: '国家平台',
  external: '外部接入',
};
const CAP_STATUS_LABELS: Record<string, string> = {
  live: '已上线',
  external: '外部契约',
};
function capStatusLabel(s: string): string {
  if (CAP_STATUS_LABELS[s]) return CAP_STATUS_LABELS[s];
  if (s.startsWith('deferred')) return '规划中';
  return s;
}
function surfaceLabel(s: string): string {
  return SURFACE_LABELS[s] ?? s;
}

const PKG_STATUS_LABELS: Record<string, string> = {
  pending: '待审',
  'pending-fix': '退回补充',
  approved: '已批准',
  active: '已启用',
  'rolled-back': '已回滚',
  suspended: '已停用',
  rejected: '已驳回',
  revoked: '已撤销',
};
const TRUST_LABELS: Record<string, string> = {
  baseline: '基线（默认）',
  reviewed: '已审',
  restricted: '严管',
  revoked: '撤回',
};

// ---- 能力总览：按来源（execution_binding）现算，自洽 5↔238 ----
const totalCount = computed(() => matrix.data.value?.totals.manifests ?? 0);
const builtinCount = computed(() => matrix.data.value?.totals.by_execution_binding?.['builtin'] ?? 0);
const externalCapCount = computed(
  () => matrix.data.value?.totals.by_execution_binding?.['external_capability'] ?? 0
);
const externalSystemCount = computed(() => packages.data.value?.items.length ?? 0);

// 按业务域分布（by_journey，人话）——与来源是两个正交切面，分别如实展示，不强行对齐数字。
const domainBreakdown = computed(() => {
  const by = matrix.data.value?.totals.by_journey ?? {};
  const order = ['j1', 'j2', 'b1', 'infra', 'national', 'external'];
  return order
    .filter((k) => by[k])
    .map((k) => ({ key: k, label: JOURNEY_LABELS[k] ?? k, count: by[k] }));
});

// 人话化浏览：按来源筛选能力，展示中文名 + 说明 + 消费面，slug 降级为次要技术编号。
type BrowseMode = 'builtin' | 'external_capability';
const browseMode = ref<BrowseMode>('builtin');
const BROWSE_CAP = 40;
const browseRows = computed(() => {
  const rows = matrix.data.value?.matrix ?? [];
  return rows.filter((r) => r.execution_binding === browseMode.value);
});
const browseShown = computed(() => browseRows.value.slice(0, BROWSE_CAP));
</script>

<template>
  <main class="focus-page">
    <section class="panel panel-stack">
      <PageFocusHeader title="接入扩展中心" meta="面向平台管理员：看清平台能力的来源、治理外部系统接入、配置审批与表单流程">
        <template #aside>
          <NLAcceleratorPanel page-anchor="B1.2" :presets="NL_PRESETS_B12" @action="consumeNLAction" />
        </template>
      </PageFocusHeader>

      <div class="focus-tab-row">
        <nav class="focus-tabs" role="tablist" aria-label="接入治理与配置">
          <span class="axis-label">治理</span>
          <button
            v-for="t in GOV_TABS"
            :key="t.key"
            type="button"
            role="tab"
            class="focus-tab"
            :class="{ active: activeTab === t.key }"
            :aria-selected="activeTab === t.key"
            @click="switchTab(t.key)"
          >
            {{ t.label }}
          </button>
          <a class="focus-tab focus-tab-link" href="#/integration-admin/iam-governance">身份治理</a>
          <span class="axis-divider" aria-hidden="true"></span>
          <span class="axis-label">配置</span>
          <button
            v-for="t in CFG_TABS"
            :key="t.key"
            type="button"
            role="tab"
            class="focus-tab"
            :class="{ active: activeTab === t.key }"
            :aria-selected="activeTab === t.key"
            @click="switchTab(t.key)"
          >
            {{ t.label }}
          </button>
        </nav>
        <button type="button" class="focus-tab refresh-btn" @click="refreshActive">刷新</button>
      </div>

      <!-- ===== 能力总览：来源叙事，消除 5↔238 困惑 ===== -->
      <section v-show="activeTab === 'overview'" class="focus-section">
        <header class="focus-section-head">
          <h2 class="focus-section-title">能力总览</h2>
          <p class="focus-section-hint">
            平台共 <strong>{{ totalCount }}</strong> 项能力 —— 同一能力底座，两种来源、两套准入强度。
          </p>
          <DataSourceBadge :source="matrix.source.value" />
        </header>

        <div class="source-grid">
          <article class="source-card">
            <div class="source-head">
              <span class="source-emoji" aria-hidden="true">🏛</span>
              <h3 class="source-title">平台内置</h3>
              <span class="source-count">{{ builtinCount }} 项</span>
            </div>
            <p class="source-desc">产品自带、默认可信，是平台能力的底座。</p>
            <p class="source-note">
              可扩展：由研发按能力注册路径新增（能力声明 + 处理器 + 评审 + 上线），
              <strong>非运行时自助新增</strong>——改执行逻辑必须过评审与部署。
            </p>
            <button type="button" class="link-btn" @click="browseMode = 'builtin'">浏览内置能力 ↓</button>
          </article>

          <article class="source-card">
            <div class="source-head">
              <span class="source-emoji" aria-hidden="true">🛂</span>
              <h3 class="source-title">外部接入</h3>
              <span class="source-count">{{ externalCapCount }} 项 · {{ externalSystemCount }} 个系统</span>
            </div>
            <p class="source-desc">外来系统经海关审批接入、需信任评估，是合法的扩展路径。</p>
            <p class="source-note source-note--warn">
              当前「审批接入」治理已就位；外部能力的<strong>实际运行时调用</strong>待执行桥（AgentRuntime）打通——
              已接入 ≠ 已能跑。
            </p>
            <button type="button" class="link-btn" @click="switchTab('external')">管理外部接入 →</button>
          </article>
        </div>

        <div class="domain-row" v-if="domainBreakdown.length">
          <span class="domain-label">按业务域分布：</span>
          <span v-for="d in domainBreakdown" :key="d.key" class="status-pill">{{ d.label }} {{ d.count }}</span>
        </div>

        <!-- 人话化浏览（替代原 238 行 slug 矩阵） -->
        <div class="browse-block">
          <div class="browse-switch" role="tablist" aria-label="按来源浏览能力">
            <button
              type="button"
              class="focus-tab focus-tab--sm"
              :class="{ active: browseMode === 'builtin' }"
              @click="browseMode = 'builtin'"
            >
              平台内置（{{ builtinCount }}）
            </button>
            <button
              type="button"
              class="focus-tab focus-tab--sm"
              :class="{ active: browseMode === 'external_capability' }"
              @click="browseMode = 'external_capability'"
            >
              外部接入（{{ externalCapCount }}）
            </button>
          </div>
          <ul v-if="browseShown.length" class="cap-list">
            <li v-for="row in browseShown" :key="row.skill_id" class="cap-item">
              <div class="cap-line1">
                <span class="cap-name">{{ row.name || row.skill_id }}</span>
                <span class="cap-status">{{ capStatusLabel(row.status) }}</span>
                <span class="cap-journey">{{ JOURNEY_LABELS[row.journey] ?? row.journey }}</span>
              </div>
              <p v-if="row.description" class="cap-desc">{{ row.description }}</p>
              <div class="cap-line3">
                <span class="cap-surface-label">开放在：</span>
                <span v-for="s in row.surfaces" :key="s" class="surface-pill">{{ surfaceLabel(s) }}</span>
                <span class="cap-techid" :title="row.skill_id">技术编号 {{ row.skill_id }}</span>
              </div>
            </li>
          </ul>
          <p v-else class="focus-prose focus-prose--muted">
            {{ matrix.source.value === 'loading' ? '正在加载……' : '该来源暂无能力。' }}
          </p>
          <p v-if="browseRows.length > BROWSE_CAP" class="focus-prose focus-prose--muted">
            仅显示前 {{ BROWSE_CAP }} 项（共 {{ browseRows.length }} 项）。
          </p>
        </div>
      </section>

      <!-- ===== 外部接入：5 个外来系统的审批治理 ===== -->
      <section v-show="activeTab === 'external'" class="focus-section">
        <header class="focus-section-head">
          <h2 class="focus-section-title">已接入的外部系统</h2>
          <p class="focus-section-hint">外来系统（如网关、诊断工具）带来的能力需经平台审批后才能启用——在此批准、停用或回退。</p>
          <DataSourceBadge :source="packages.source.value" />
        </header>
        <p class="disclaimer">
          这里管的是<strong>外部系统的准入</strong>：审批、信任级评估、开放范围收口。
          注意——审批接入治理已就位，但<strong>外部能力的实际运行时调用待执行桥（AgentRuntime）打通</strong>，「已接入」不等于「已能跑」。
        </p>
        <p class="disclaimer">
          「内置信任级」是<strong>本平台对外部系统的信任评估</strong>（四档：基线 / 已审 / 严管 / 撤回），
          由运营管理员评估后决定能否启用；与外部智能体来源信任级不是同一字段。
        </p>
        <table v-if="packages.data.value && packages.data.value.items.length" class="pkg-table">
          <thead>
            <tr><th>外部系统</th><th>状态</th><th>当前版本</th><th>上一版本</th><th>信任级</th><th>技术编号</th><th>操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="p in packages.data.value.items" :key="p.id">
              <td><a :href="`#/integration-admin/package/${p.id}`">{{ p.name || p.id }}</a></td>
              <td><span :class="['status-pill', `status-${p.status}`]">{{ PKG_STATUS_LABELS[p.status] ?? p.status }}</span></td>
              <td><span class="tech-id">{{ p.version || '—' }}</span></td>
              <td><span class="tech-id">{{ p.rollback_target || '—' }}</span></td>
              <td>
                <span :class="['trust-pill', trustPillClass(p.trust_level)]">
                  {{ TRUST_LABELS[p.trust_level] ?? p.trust_level }}
                </span>
              </td>
              <td><span class="tech-id">{{ p.id }}</span></td>
              <td class="actions">
                <button class="gov-btn gov-btn-primary" @click="onReview(p.id, 'approve')" :disabled="p.status === 'active' || p.status === 'rejected' || p.status === 'revoked'">批准</button>
                <button class="gov-btn gov-btn-secondary" @click="onReview(p.id, 'return_for_fix')" :disabled="p.status !== 'pending'">退回</button>
                <button class="gov-btn gov-btn-secondary" @click="onEnable(p.id)" :disabled="p.status !== 'approved' && p.status !== 'rolled-back'">启用</button>
                <button class="gov-btn gov-btn-secondary" @click="onDisable(p.id)" :disabled="p.status !== 'active'">停用</button>
                <button class="gov-btn gov-btn-warn" @click="onRollback(p.id)" :disabled="!p.rollback_target">回滚</button>
                <button class="gov-btn gov-btn-secondary" @click="onTrustLevelChange(p.id)">改信任级</button>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-else class="focus-prose focus-prose--muted">{{ packages.source.value === 'loading' ? '正在加载……' : '暂无接入的外部系统。' }}</p>
      </section>

      <!-- ===== 配置轴：流程与表单配置 ===== -->
      <section v-show="activeTab === 'engines'" class="focus-section">
        <header class="focus-section-head">
          <h2 class="focus-section-title">流程与表单配置</h2>
          <p class="focus-section-hint">审批流程、申请表单与智能推荐属业务定制——与接入治理是两类事，故单列一轴。</p>
        </header>
        <p class="disclaimer">
          审批流程、申请表单与智能推荐的配置集中在
          <a href="#/integration-admin/engines">配置页</a>；本面板提供快捷入口。
        </p>
        <div class="slot-grid">
          <a v-for="slot in slots" :key="slot.key" :href="slot.href" class="slot-card">
            <h3>{{ slot.title }}</h3>
            <p>{{ slot.subtitle }}</p>
            <p class="slot-status">{{ slot.status === 'available' ? '可用' : (slot.pending_reason || '待上线') }}</p>
          </a>
        </div>
      </section>
    </section>
  </main>
</template>

<style scoped>
.disclaimer {
  font-size: 13px;
  line-height: 1.6;
  color: var(--b-muted, #5c6370);
  margin: 0 0 12px;
  padding: 12px 14px;
  background: var(--b-bg-subtle, #e8f2fc);
  border-radius: 6px;
  border-left: 3px solid var(--b-primary, #006be6);
}
/* 来源卡 */
.source-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 14px; margin: 6px 0 14px; }
.source-card { padding: 16px 18px; background: #fff; border: 1px solid var(--b-border, #d4e2f4); border-radius: 10px; }
.source-head { display: flex; align-items: baseline; gap: 8px; margin-bottom: 8px; }
.source-emoji { font-size: 18px; }
.source-title { margin: 0; font-size: 16px; color: var(--b-neutral-text, #1a1d21); }
.source-count { margin-left: auto; font-size: 14px; font-weight: 700; color: var(--b-primary, #006be6); }
.source-desc { margin: 0 0 6px; font-size: 13px; color: var(--b-neutral-text, #1a1d21); }
.source-note { margin: 0 0 10px; font-size: 12.5px; line-height: 1.6; color: var(--b-muted, #5c6370); }
.source-note--warn { color: #856404; background: #fff8e6; padding: 8px 10px; border-radius: 6px; }
.link-btn { background: none; border: none; color: var(--b-primary, #006be6); font-size: 13px; cursor: pointer; padding: 0; }
.domain-row { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin: 0 0 16px; }
.domain-label { font-size: 13px; color: var(--b-muted, #5c6370); font-weight: 600; }
/* 人话浏览列表 */
.browse-block { margin-top: 6px; }
.browse-switch { display: flex; gap: 8px; margin-bottom: 10px; }
.focus-tab--sm { padding: 4px 12px; font-size: 12.5px; }
.cap-list { list-style: none; margin: 0; padding: 0; }
.cap-item { padding: 12px 0; border-bottom: 1px solid var(--b-border, #d4e2f4); }
.cap-line1 { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.cap-name { font-size: 14px; font-weight: 600; color: var(--b-neutral-text, #1a1d21); }
.cap-status { font-size: 12px; padding: 1px 8px; border-radius: 999px; background: #d4f8e0; color: #155724; }
.cap-journey { font-size: 12px; padding: 1px 8px; border-radius: 999px; background: var(--b-bg-subtle, #e8f2fc); color: var(--b-muted, #5c6370); }
.cap-desc { margin: 4px 0 6px; font-size: 12.5px; line-height: 1.6; color: var(--b-muted, #5c6370); }
.cap-line3 { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.cap-surface-label { font-size: 12px; color: var(--b-muted, #5c6370); }
.surface-pill { font-size: 12px; padding: 1px 8px; border-radius: 999px; background: var(--b-bg-subtle, #e8f2fc); color: var(--b-primary, #006be6); }
.cap-techid { margin-left: auto; font-size: 11px; color: #9aa4b2; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.pkg-table { width: 100%; border-collapse: collapse; margin-top: 12px; }
.pkg-table th, .pkg-table td { padding: 10px 12px; text-align: left; font-size: 13px; border-bottom: 1px solid var(--b-border, #d4e2f4); }
.pkg-table th { background: var(--b-bg-subtle, #e8f2fc); color: var(--b-muted, #5c6370); font-weight: 600; }
.status-pill { background: var(--b-bg-subtle, #e8f2fc); color: var(--b-primary, #006be6); font-size: 12px; padding: 2px 8px; border-radius: 999px; margin-right: 4px; display: inline-block; }
.status-pill.status-active { background: #d4f8e0; color: #155724; }
.status-pill.status-pending { background: #fff3cd; color: #856404; }
.status-pill.status-rejected, .status-pill.status-revoked { background: #f8d7da; color: #842029; }
.status-pill.status-rolled-back { background: #cfe2ff; color: #084298; }
.trust-pill { font-size: 12px; padding: 2px 10px; border-radius: 999px; white-space: nowrap; display: inline-block; }
.trust-pill.trust-baseline { background: var(--b-bg-subtle, #e8f2fc); color: var(--b-muted, #5c6370); }
.trust-pill.trust-reviewed { background: #d4f8e0; color: #155724; }
.trust-pill.trust-restricted { background: #fff3cd; color: #856404; }
.trust-pill.trust-revoked { background: #f8d7da; color: #842029; }
.tech-id { font-size: 11px; color: #9aa4b2; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.actions { display: flex; flex-wrap: wrap; gap: 4px; }
.gov-btn { padding: 4px 8px; border-radius: 4px; font-size: 12px; cursor: pointer; border: 1px solid transparent; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
.gov-btn-secondary { background: #fff; border: 1px solid var(--b-border, #d4e2f4); color: var(--b-neutral-text, #1a1d21); }
.gov-btn-warn { background: #f0ad4e; color: #fff; }
.gov-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.slot-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; margin-top: 12px; }
.slot-card { padding: 14px 16px; background: #fff; border: 1px solid var(--b-border, #d4e2f4); border-radius: 8px; text-decoration: none; color: inherit; transition: border-color 0.15s; }
.slot-card:hover { border-color: var(--b-primary, #006be6); }
.slot-card h3 { margin: 0 0 6px; font-size: 14px; color: var(--b-primary, #006be6); }
.slot-card p { margin: 4px 0; font-size: 12px; color: var(--b-muted, #5c6370); }
.slot-status { font-weight: 600; }
.focus-section-hint { margin: 4px 0 10px; font-size: 13px; color: var(--b-muted, #5c6370); }
.axis-label { font-size: 12px; font-weight: 600; color: var(--b-muted, #5c6370); letter-spacing: 0.05em; align-self: center; padding: 0 2px; }
.axis-divider { width: 1px; align-self: stretch; margin: 4px 8px; background: var(--b-border, #d4e2f4); }
.focus-tab-link { text-decoration: none; display: inline-flex; align-items: center; }
</style>
