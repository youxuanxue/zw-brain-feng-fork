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

// B1.2 接入扩展中心：3 tab——能力包注册表 / 暴露范围矩阵 / 三引擎入口；
// 仅 ROLE_SECURITY_ADMIN / ROLE_BUSIAUDIT 可见（后端 policy.py 已限）。
//
// 设计意图：
//   1. 信任级 trust_level 在 UI 显示时**明确标注**为「能力包内置信任级」
//      （baseline/reviewed/restricted/revoked），与 F6 T1 触发后的 AgentRuntime
//      Registry trust_level（外部 Agent 来源信任级 platform/verified/untrusted）
//      不是同一字段。UI 上 disclaimer 行明示。
//   2. 写操作（审核/启停/回滚/信任级升降级）严格走 window.confirm() 二次确认；
//      与后端 manifest human_confirmation_required=true 对齐。
//   3. 三引擎 slot 不重实装；本 UI 列 3 个入口跳转到 E3 已 land 的
//      /engines-admin（B13EnginesAdmin.vue 内 tab 切换），见 useEngineSlots.ts。

type TabKind = 'list' | 'matrix' | 'engines';
const activeTab = ref<TabKind>('list');

const NL_PRESETS_B12 = ['未审核能力包', '近 7 天 IAM 失败', '看接入故障'];

const packages = usePackageList();
const matrix = useExposureMatrix();
const { slots } = useEngineSlots();

const matrixJourneyFilter = ref('');
const matrixStatusFilter = ref('');

onMounted(() => {
  void packages.load();
  void matrix.load({});
});

function switchTab(t: TabKind): void {
  activeTab.value = t;
}

async function refreshActive(): Promise<void> {
  if (activeTab.value === 'list') await packages.load();
  else if (activeTab.value === 'matrix') {
    await matrix.load({
      journey: matrixJourneyFilter.value || undefined,
      status: matrixStatusFilter.value || undefined,
    });
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
  if (!window.confirm(`确认对能力包 ${pkgId} 执行「${label}」？此操作会写审计 + 持久化。`)) return;
  const r = await reviewPackage(pkgId, decision, true);
  if (r.ok) {
    pushToast({ kind: 'ok', title: '已落审计', detail: `${pkgId} · ${label} · audit_id=${r.audit_id ?? '—'}` });
    await packages.load();
  } else {
    pushToast({ kind: 'error', title: '审核失败', detail: r.error ?? '后端报错' });
  }
}

async function onEnable(pkgId: string): Promise<void> {
  if (!window.confirm(`确认启用能力包 ${pkgId}？启用后此能力可被本租户调用。`)) return;
  const r = await enableTenantCapability(pkgId, true);
  pushToast(r.ok
    ? { kind: 'ok', title: '已启用', detail: pkgId }
    : { kind: 'error', title: '启用失败', detail: r.error ?? '—' });
  if (r.ok) await packages.load();
}

async function onDisable(pkgId: string): Promise<void> {
  if (!window.confirm(`确认停用能力包 ${pkgId}？停用后本租户调用该能力会被拦下。`)) return;
  const r = await disableTenantCapability(pkgId, true);
  pushToast(r.ok
    ? { kind: 'ok', title: '已停用', detail: pkgId }
    : { kind: 'error', title: '停用失败', detail: r.error ?? '—' });
  if (r.ok) await packages.load();
}

async function onRollback(pkgId: string): Promise<void> {
  const reason = window.prompt(`请说明回滚原因（必填）：\n能力包 ${pkgId}`);
  if (!reason) return;
  if (!window.confirm(`将能力包 ${pkgId} 回滚到上一版本？\n原因：${reason}`)) return;
  const r = await rollbackPackage(pkgId, reason, true);
  pushToast(r.ok
    ? { kind: 'ok', title: '已回滚', detail: `${pkgId} · ${String(r.result?.rolled_back_to ?? '—')}` }
    : { kind: 'error', title: '回滚失败', detail: r.error ?? '—' });
  if (r.ok) await packages.load();
}

async function onTrustLevelChange(pkgId: string): Promise<void> {
  const target = window.prompt(
    `升降能力包 ${pkgId} 的内置信任级，请输入目标级别：\nbaseline / reviewed / restricted / revoked`
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

const matrixSurfaces = computed(() => {
  const totals = matrix.data.value?.totals.by_surface ?? {};
  return Object.entries(totals).map(([k, v]) => ({ key: k, value: v }));
});

const STATUS_LABELS: Record<string, string> = {
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
</script>

<template>
  <main class="focus-page">
    <section class="panel panel-stack">
      <PageFocusHeader title="接入扩展中心" meta="能力包 · 暴露矩阵 · 信任级">
        <template #aside>
          <NLAcceleratorPanel page-anchor="B1.2" :presets="NL_PRESETS_B12" @action="consumeNLAction" />
        </template>
      </PageFocusHeader>

      <div class="focus-tab-row">
        <nav class="focus-tabs" role="tablist">
          <button
            v-for="t in (['list', 'matrix', 'engines'] as TabKind[])"
            :key="t"
            type="button"
            role="tab"
            class="focus-tab"
            :class="{ active: activeTab === t }"
            :aria-selected="activeTab === t"
            @click="switchTab(t)"
          >
            {{ t === 'list' ? '能力包注册' : t === 'matrix' ? '暴露范围矩阵' : '三引擎入口' }}
          </button>
        </nav>
        <button type="button" class="focus-tab refresh-btn" @click="refreshActive">刷新</button>
      </div>

      <section v-show="activeTab === 'list'" class="focus-section">
        <header class="focus-section-head">
          <h2 class="focus-section-title">能力包注册表</h2>
          <DataSourceBadge :source="packages.source.value" />
        </header>
        <p class="disclaimer">
          「内置信任级」是<strong>本平台对能力包的信任评估</strong>（四档：基线 / 已审 / 严管 / 撤回），由运营管理员评估后决定能否启用；
          与外部智能体来源信任级不是同一字段。
        </p>
        <table v-if="packages.data.value && packages.data.value.items.length" class="pkg-table">
        <thead>
          <tr><th>编号</th><th>名称</th><th>状态</th><th>当前版本</th><th>上一版本</th><th>信任级</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="p in packages.data.value.items" :key="p.id">
            <td><span class="tech-id">{{ p.id }}</span></td>
            <td>{{ p.name || '—' }}</td>
            <td><span :class="['status-pill', `status-${p.status}`]">{{ STATUS_LABELS[p.status] ?? p.status }}</span></td>
            <td><span class="tech-id">{{ p.version || '—' }}</span></td>
            <td><span class="tech-id">{{ p.rollback_target || '—' }}</span></td>
            <td>
              <span :class="['trust-pill', trustPillClass(p.trust_level)]">
                {{ TRUST_LABELS[p.trust_level] ?? p.trust_level }}
              </span>
            </td>
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
      <p v-else class="focus-prose focus-prose--muted">{{ packages.source.value === 'loading' ? '正在加载……' : '暂无注册能力包。' }}</p>
      </section>

      <section v-show="activeTab === 'matrix'" class="focus-section">
        <header class="focus-section-head">
          <h2 class="focus-section-title">暴露范围矩阵</h2>
          <div class="focus-section-controls">
          <label>所属旅程：
            <select v-model="matrixJourneyFilter" @change="matrix.load({ journey: matrixJourneyFilter || undefined, status: matrixStatusFilter || undefined })">
              <option value="">全部</option>
              <option value="j1">J1 找数→用数</option>
              <option value="j2">J2 挂数→维数</option>
              <option value="b1">B1 后台支撑</option>
              <option value="infra">基础设施</option>
              <option value="external">外部</option>
            </select>
          </label>
          <label>能力状态：
            <select v-model="matrixStatusFilter" @change="matrix.load({ journey: matrixJourneyFilter || undefined, status: matrixStatusFilter || undefined })">
              <option value="">全部</option>
              <option value="live">已上线</option>
              <option value="external">外部</option>
              <option value="deferred:wave-2">延后到 Wave-2</option>
            </select>
          </label>
          <DataSourceBadge :source="matrix.source.value" />
          </div>
        </header>
        <p v-if="matrix.data.value" class="focus-prose">
        共 <strong>{{ matrix.data.value.totals.manifests }}</strong> 份能力契约；
        本次筛选 <strong>{{ matrix.data.value.scanned }}</strong> 行。各消费面分布：
        <span v-for="s in matrixSurfaces" :key="s.key" class="status-pill">{{ s.key }}: {{ s.value }}</span>
      </p>
      <table v-if="matrix.data.value && matrix.data.value.matrix.length" class="pkg-table">
        <thead>
          <tr><th>能力编号</th><th>旅程</th><th>状态</th><th>执行绑定</th><th>审计等级</th><th>需二次确认</th><th>消费面</th><th>信任级</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in matrix.data.value.matrix" :key="row.skill_id">
            <td><span class="tech-id">{{ row.skill_id }}</span></td>
            <td>{{ row.journey }}</td>
            <td><span :class="['status-pill', `status-${row.status.replace(':', '-')}`]">{{ row.status }}</span></td>
            <td>{{ row.execution_binding }}</td>
            <td><span class="status-pill">{{ row.audit_class }}</span></td>
            <td>{{ row.human_confirmation_required ? '✓' : '—' }}</td>
            <td>
              <span v-for="s in row.surfaces" :key="s" class="status-pill">{{ s }}</span>
            </td>
            <td>
              <span :class="['trust-pill', trustPillClass(row.trust_level)]">
                {{ TRUST_LABELS[row.trust_level] ?? row.trust_level }}
              </span>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="focus-prose focus-prose--muted">{{ matrix.source.value === 'loading' ? '正在加载……' : '当前筛选无数据。' }}</p>
      </section>

      <section v-show="activeTab === 'engines'" class="focus-section">
        <header class="focus-section-head">
          <h2 class="focus-section-title">三引擎入口</h2>
        </header>
      <p class="disclaimer">
        三引擎（审批流 / 表单 / 智能推荐前置）的管理员配置面已集中在
        <a href="#/engines-admin">三引擎配置中心</a>；本面板仅提供入口链接。
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
.pkg-table { width: 100%; border-collapse: collapse; margin-top: 12px; }
.pkg-table th, .pkg-table td { padding: 10px 12px; text-align: left; font-size: 13px; border-bottom: 1px solid var(--b-border, #d4e2f4); }
.pkg-table th { background: var(--b-bg-subtle, #e8f2fc); color: var(--b-muted, #5c6370); font-weight: 600; }
.status-pill { background: var(--b-bg-subtle, #e8f2fc); color: var(--b-primary, #006be6); font-size: 12px; padding: 2px 8px; border-radius: 999px; margin-right: 4px; display: inline-block; }
.status-pill.status-active { background: #d4f8e0; color: #155724; }
.status-pill.status-pending { background: #fff3cd; color: #856404; }
.status-pill.status-rejected, .status-pill.status-revoked { background: #f8d7da; color: #842029; }
.status-pill.status-rolled-back { background: #cfe2ff; color: #084298; }
.trust-pill {
  font-size: 12px;
  padding: 2px 10px;
  border-radius: 999px;
  white-space: nowrap;
  display: inline-block;
}
.trust-pill.trust-baseline { background: var(--b-bg-subtle, #e8f2fc); color: var(--b-muted, #5c6370); }
.trust-pill.trust-reviewed { background: #d4f8e0; color: #155724; }
.trust-pill.trust-restricted { background: #fff3cd; color: #856404; }
.trust-pill.trust-revoked { background: #f8d7da; color: #842029; }
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
</style>
