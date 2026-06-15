<script setup lang="ts">
import { onMounted } from 'vue';
import {
  disableTenantCapability,
  enableTenantCapability,
  reviewPackage,
  updatePackageTrustLevel,
  usePackageList,
} from '@/composables/usePackageLifecycle';
import { pushToast } from '@/composables/useActionStub';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DataSourceBadge from '@/components/DataSourceBadge.vue';
import NLAcceleratorPanel from '@/components/NLAcceleratorPanel.vue';
import { consumeNLAction } from '@/lib/consumeNLAction';
import { trustPillClass, TRUST_LABELS, PKG_STATUS_LABELS } from '@/lib/packageDisplay';

// 外部系统 —— 外来系统接入治理的独立模块（「接入扩展中心」容器已解体，负责人 2026-06-05 裁）。
// 一页到底，无内部 tab：账目行（诚实能力计数）→ 系统表（审批 / 启停 / 信任级）。
// 瘦身（2026-06-05）：只留运营员真能动手且有后果的东西——
//   · 砍「外部能力契约」逐条清单（14↔5 无归属字段、单条不可操作、运行时跑不了）；
//   · 砍账目行（内置 194 与本页无关；系统数/启用数表格自明；诚实信号页头 meta 已说一次）——
//     随之退役 exposure-matrix 查询，本页只发 package.list；
//   · 砍「当前版本/上一版本」空列 + 「技术编号」列（移详情）；
//   · 操作改 v-if 只渲染当前可执行项（无永久灰按钮）；回滚撤出（无版本历史时是假按钮）。
//
// 词表纪律（一词一概念）：「外部系统」= 治理对象（导航/页头/表头/详情同词）；
// 「外部接入」只作来源叙事形容词。
//
// 诚实校准：已接入 ≠ 已能跑（待执行桥 AgentRuntime 打通），页头 meta 说一次，不重复。
//
// 仅 ROLE_SYSTEM 可见（0609 权限梳理 P2 外部系统收归平台运维员；productShellNav 角色门 + 路由 beforeEach 守卫）。

const NL_PRESETS_B12 = ['未审核能力包', '近 7 天 IAM 失败', '看接入故障'];

const packages = usePackageList();

onMounted(() => {
  void packages.load();
});

async function refreshAll(): Promise<void> {
  await packages.load();
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

// 人话标签映射（PKG_STATUS_LABELS / TRUST_LABELS）已收口到 lib/packageDisplay.ts 单源
// （R-019④），本页直接 import 复用，避免逐字副本分叉（R12 段24/24b）。

</script>

<template>
  <main class="focus-page">
    <section class="panel panel-stack">
      <PageFocusHeader title="外部系统" meta="外来系统经平台审批接入、信任评估与启停——已接入 ≠ 已能跑">
        <template #aside>
          <NLAcceleratorPanel page-anchor="B1.2" :presets="NL_PRESETS_B12" @action="consumeNLAction" />
        </template>
      </PageFocusHeader>

      <section class="focus-section">
        <header class="focus-section-head">
          <h2 class="focus-section-title">已接入的外部系统</h2>
          <p class="focus-section-hint">外来系统（如网关、诊断工具）带来的能力需经平台审批后才能启用——在此审批、启停、定信任级。</p>
          <DataSourceBadge :source="packages.source.value" />
          <button type="button" class="focus-tab refresh-btn" @click="refreshAll">刷新</button>
        </header>
        <p class="disclaimer">
          「内置信任级」是<strong>本平台对外部系统的信任评估</strong>（四档：基线 / 已审 / 严管 / 撤回），
          由运营管理员评估后决定能否启用；与外部智能体来源信任级不是同一字段。
        </p>
        <table v-if="packages.data.value && packages.data.value.items.length" class="pkg-table">
          <thead>
            <tr><th>外部系统</th><th>状态</th><th>信任级</th><th>操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="p in packages.data.value.items" :key="p.id">
              <td>
                <a :href="`#/integration-admin/package/${p.id}`" class="sys-name">{{ p.name || p.id }}</a>
                <p v-if="p.desc" class="sys-desc">{{ p.desc }}</p>
              </td>
              <td><span :class="['status-pill', `status-${p.status}`]">{{ PKG_STATUS_LABELS[p.status] ?? p.status }}</span></td>
              <td>
                <span :class="['trust-pill', trustPillClass(p.trust_level)]">
                  {{ TRUST_LABELS[p.trust_level] ?? p.trust_level }}
                </span>
              </td>
              <td class="actions">
                <!-- 只渲染当前状态下真能执行的操作，无永久灰按钮（回滚需版本历史，到详情页再做） -->
                <template v-if="p.status === 'pending'">
                  <button class="gov-btn gov-btn-primary" @click="onReview(p.id, 'approve')">批准</button>
                  <button class="gov-btn gov-btn-secondary" @click="onReview(p.id, 'return_for_fix')">退回</button>
                </template>
                <button v-if="p.status === 'approved' || p.status === 'rolled-back'" class="gov-btn gov-btn-primary" @click="onEnable(p.id)">启用</button>
                <button v-if="p.status === 'active'" class="gov-btn gov-btn-secondary" @click="onDisable(p.id)">停用</button>
                <button class="gov-btn gov-btn-secondary" @click="onTrustLevelChange(p.id)">改信任级</button>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-else-if="packages.error.value" class="focus-prose focus-prose--muted">外部系统列表加载失败，请稍后重试或联系平台运维员。</p>
        <p v-else class="focus-prose focus-prose--muted">{{ packages.source.value === 'loading' ? '正在加载……' : '暂无接入的外部系统。' }}</p>
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
.refresh-btn { margin-left: auto; }
/* 外部系统表 */
.pkg-table { width: 100%; border-collapse: collapse; margin-top: 12px; }
.pkg-table th, .pkg-table td { padding: 10px 12px; text-align: left; font-size: 13px; border-bottom: 1px solid var(--b-border, #d4e2f4); vertical-align: top; }
.pkg-table th { background: var(--b-bg-subtle, #e8f2fc); color: var(--b-muted, #5c6370); font-weight: 600; }
.sys-name { font-weight: 600; color: var(--b-primary, #006be6); text-decoration: none; }
.sys-name:hover { text-decoration: underline; }
.sys-desc { margin: 4px 0 0; font-size: 12px; line-height: 1.5; color: var(--b-muted, #5c6370); max-width: 420px; }
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
.actions { display: flex; flex-wrap: wrap; gap: 4px; }
.gov-btn { padding: 4px 8px; border-radius: 4px; font-size: 12px; cursor: pointer; border: 1px solid transparent; }
.gov-btn-primary { background: var(--b-primary, #006be6); color: #fff; }
.gov-btn-secondary { background: #fff; border: 1px solid var(--b-border, #d4e2f4); color: var(--b-neutral-text, #1a1d21); }
.gov-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.focus-section-hint { margin: 4px 0 10px; font-size: 13px; color: var(--b-muted, #5c6370); }
</style>
