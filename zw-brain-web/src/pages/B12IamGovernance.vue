<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DataSourceBadge from '@/components/DataSourceBadge.vue';
import { usePolicyCandidates } from '@/composables/usePolicyCandidates';
import { useActorGovernance } from '@/composables/useActorGovernance';
import type { PolicyCandidateItem } from '@/fixtures/b12-iam-fixture';
import type { ActorItem } from '@/fixtures/actor-governance-fixture';
import { pushToast } from '@/composables/useActionStub';
import { getProductRole } from '@/composables/useProductRole';
import { PRODUCT_ROLE_LABELS } from '@/composables/useAuth';

const role = getProductRole();

// ── Tab 状态 ───────────────────────────────────────────────
type TabKey = 'actors' | 'matrix' | 'policy';
const activeTab = ref<TabKey>('actors');
const TABS: ReadonlyArray<{ key: TabKey; label: string }> = [
  { key: 'actors', label: '用户与角色' },
  { key: 'matrix', label: '谁能访问什么' },
  { key: 'policy', label: '旧权限映射审核' },
];
function switchTab(key: TabKey): void {
  if (activeTab.value === key) return;
  activeTab.value = key;
  if (key === 'matrix' && gov.matrixSource.value === 'idle') void reloadMatrix();
}

// ── 共享：可分配角色码（PRODUCT_ROLE_LABELS 单源，与 useAuth 5 业务角色对齐）───
const ASSIGNABLE_ROLES = Object.keys(PRODUCT_ROLE_LABELS);
function roleLabel(code: string): string {
  return PRODUCT_ROLE_LABELS[code] ?? code;
}

const ACTOR_STATUS_LABELS: Record<string, string> = {
  active: '已启用',
  iam_account_missing: '待绑定 IAM',
  unmatched: '未匹配',
  disabled: '已停用',
};
function actorStatusLabel(s: string): string {
  return ACTOR_STATUS_LABELS[s] ?? s;
}
function actorStatusTone(s: string): string {
  if (s === 'active') return 'tone-ok';
  if (s === 'disabled') return 'tone-neutral';
  if (s === 'unmatched') return 'tone-danger';
  return 'tone-warn'; // iam_account_missing
}

// ════════════════════════════════════════════════════════════
// Tab ① 用户与角色（actor list + 分派/撤销角色 + 启停）
// ════════════════════════════════════════════════════════════
const gov = useActorGovernance();

const actorQ = ref('');
const actorOrgFilter = ref('');
const actorRoleFilter = ref('');
const actorStatusFilter = ref('');

const canWrite = computed(() => gov.actorSource.value === 'live');

const actorItems = computed<ActorItem[]>(() => gov.actorData.value?.items ?? []);

const actorSummaryText = computed(() => {
  const summary = gov.actorData.value?.summary;
  if (!summary) return '—';
  const parts = Object.entries(summary.status_counts ?? {}).map(
    ([k, n]) => `${actorStatusLabel(k)} ${n}`,
  );
  return `共 ${summary.total} 名用户${parts.length ? `（${parts.join(' · ')}）` : ''}`;
});

// 行内展开「分派角色」表单：每行选择目标机构 + 目标角色后确认。
const assigningId = ref('');
const assignOrg = ref('');
const assignRoleCode = ref('');
function startAssign(item: ActorItem): void {
  assigningId.value = item.external_actor_id;
  assignOrg.value = item.org_code || '';
  assignRoleCode.value = '';
}
function cancelAssign(): void {
  assigningId.value = '';
  assignOrg.value = '';
  assignRoleCode.value = '';
}

async function reloadActors(): Promise<void> {
  await gov.listActors({
    role: role.value,
    q: actorQ.value || undefined,
    orgCode: actorOrgFilter.value || undefined,
    roleCode: actorRoleFilter.value || undefined,
    status: actorStatusFilter.value || undefined,
  });
}

function guardWrite(): boolean {
  if (!canWrite.value) {
    pushToast({
      kind: 'warn',
      title: '当前为样例数据',
      detail: '后端未连通，无法执行写操作。请先刷新并确认 live 数据源。',
    });
    return false;
  }
  return true;
}

async function confirmAssign(item: ActorItem): Promise<void> {
  if (!guardWrite()) return;
  if (!assignOrg.value.trim()) {
    pushToast({ kind: 'warn', title: '请填写机构编码', detail: '角色按机构分派，需指定目标机构。' });
    return;
  }
  if (!assignRoleCode.value) {
    pushToast({ kind: 'warn', title: '请选择角色', detail: '请选择要分派给该用户的角色。' });
    return;
  }
  const note = window.prompt('分派备注（可选）：') ?? '';
  const r = await gov.assignRole(role.value, item.external_actor_id, assignOrg.value.trim(), assignRoleCode.value, note);
  if (r.ok) {
    pushToast({
      kind: 'ok',
      title: '角色已分派',
      detail: `${item.display_name} · ${roleLabel(assignRoleCode.value)} @ ${assignOrg.value.trim()} · audit_id=${r.audit_id ?? '—'}`,
    });
    cancelAssign();
    await reloadActors();
  } else {
    pushToast({ kind: 'error', title: '分派失败', detail: r.error ?? '后端报错' });
  }
}

async function onRevoke(item: ActorItem, orgCode: string, roleCode: string): Promise<void> {
  if (!guardWrite()) return;
  if (!window.confirm(`确认撤销「${item.display_name}」在 ${orgCode} 的角色「${roleLabel(roleCode)}」？此操作会写审计。`)) {
    return;
  }
  const note = window.prompt('撤销备注（可选）：') ?? '';
  const r = await gov.revokeRole(role.value, item.external_actor_id, orgCode, roleCode, note);
  if (r.ok) {
    pushToast({ kind: 'ok', title: '角色已撤销', detail: `${item.display_name} · ${roleLabel(roleCode)} · audit_id=${r.audit_id ?? '—'}` });
    await reloadActors();
  } else {
    pushToast({ kind: 'error', title: '撤销失败', detail: r.error ?? '后端报错' });
  }
}

async function onToggleStatus(item: ActorItem): Promise<void> {
  if (!guardWrite()) return;
  const next: 'active' | 'disabled' = item.status === 'disabled' ? 'active' : 'disabled';
  const verb = next === 'disabled' ? '停用' : '启用';
  if (!window.confirm(`确认${verb}用户「${item.display_name}」？此操作会写审计。`)) {
    return;
  }
  const note = window.prompt(`${verb}备注（可选）：`) ?? '';
  const r = await gov.setStatus(role.value, item.external_actor_id, next, note);
  if (r.ok) {
    pushToast({ kind: 'ok', title: `用户已${verb}`, detail: `${item.display_name} · audit_id=${r.audit_id ?? '—'}` });
    await reloadActors();
  } else {
    pushToast({ kind: 'error', title: `${verb}失败`, detail: r.error ?? '后端报错' });
  }
}

// ════════════════════════════════════════════════════════════
// Tab ② 谁能访问什么（只读 role → capability 矩阵）
// ════════════════════════════════════════════════════════════
const matrixRoles = computed(() => gov.matrixData.value?.roles ?? []);
async function reloadMatrix(): Promise<void> {
  await gov.loadAccessMatrix(role.value);
}

// ════════════════════════════════════════════════════════════
// Tab ③ 旧权限映射审核（既有 policy-candidate 审核逐字迁入）
// ════════════════════════════════════════════════════════════
const panel = usePolicyCandidates();
const statusFilter = ref('');
const selectedKeys = ref<Set<string>>(new Set());

const POLICY_STATUS_LABELS: Record<string, string> = {
  pending_review: '待审核',
  needs_review: '需复核',
  approved: '已批准',
  rejected: '已驳回',
};

function rowKey(item: PolicyCandidateItem): string {
  return `${item.legacy_system}:${item.legacy_permission_ref}:${item.capability_id}`;
}

const canReview = computed(() => panel.source.value === 'live');
const visibleItems = computed(() => panel.data.value?.items ?? []);

const summaryText = computed(() => {
  const summary = panel.data.value?.summary;
  if (!summary) return '—';
  const parts = Object.entries(summary.status_counts ?? {}).map(
    ([k, n]) => `${POLICY_STATUS_LABELS[k] ?? k} ${n}`,
  );
  return `共 ${summary.total} 条${parts.length ? `（${parts.join(' · ')}）` : ''}`;
});

function toggleRow(item: PolicyCandidateItem, checked: boolean): void {
  const key = rowKey(item);
  const next = new Set(selectedKeys.value);
  if (checked) next.add(key);
  else next.delete(key);
  selectedKeys.value = next;
}

function toggleAll(checked: boolean): void {
  if (!checked) {
    selectedKeys.value = new Set();
    return;
  }
  selectedKeys.value = new Set(visibleItems.value.map(rowKey));
}

function selectedItems(): PolicyCandidateItem[] {
  return visibleItems.value.filter((it) => selectedKeys.value.has(rowKey(it)));
}

async function reloadPolicy(): Promise<void> {
  selectedKeys.value = new Set();
  await panel.load({ role: role.value, candidateStatus: statusFilter.value || undefined });
}

async function onReview(decision: 'approve' | 'reject' | 'approve_and_apply'): Promise<void> {
  if (!canReview.value) {
    pushToast({ kind: 'warn', title: '当前为样例数据', detail: '后端未连通，无法执行审核写操作。请先刷新并确认 live 数据源。' });
    return;
  }
  const items = selectedItems();
  if (!items.length) {
    pushToast({ kind: 'warn', title: '请先勾选候选', detail: '至少选择一条旧权限映射候选再执行审核。' });
    return;
  }
  const label =
    decision === 'reject' ? '驳回' : decision === 'approve' ? '批准（不落策略）' : '批准并写入租户策略';
  if (!window.confirm(`确认对 ${items.length} 条候选执行「${label}」？此操作会写审计并可能变更租户策略。`)) {
    return;
  }
  const note = window.prompt('审核备注（可选）：') ?? '';
  const r = await panel.review(items, decision, role.value, note);
  if (r.ok) {
    pushToast({
      kind: 'ok',
      title: '审核已落库',
      detail: `${label} · ${items.length} 条 · audit_id=${r.audit_id ?? '—'}`,
    });
    await reloadPolicy();
  } else {
    pushToast({ kind: 'error', title: '审核失败', detail: r.error ?? '后端报错' });
  }
}

onMounted(() => {
  void reloadActors();
  void reloadPolicy();
});
</script>

<template>
  <main class="focus-page">
    <section class="panel panel-stack">
      <PageFocusHeader title="身份治理" meta="用户与角色管理 · 角色能力矩阵 · 旧权限映射审核" />

      <div class="focus-tabs" role="tablist">
        <button
          v-for="t in TABS"
          :key="t.key"
          type="button"
          role="tab"
          class="focus-tab"
          :class="{ active: activeTab === t.key }"
          :aria-selected="activeTab === t.key"
          @click="switchTab(t.key)"
        >{{ t.label }}</button>
      </div>

      <!-- ════ Tab ① 用户与角色 ════ -->
      <div v-show="activeTab === 'actors'" class="tab-panel" role="tabpanel">
        <p class="disclaimer">
          管理本租户用户的角色分派与启停。角色按机构（org_code）分派；停用后用户不再继承任何角色权限。
          所有写操作均写审计；当前数据源非实时（live）时写操作禁用。
        </p>

        <div class="focus-tab-row">
          <label class="filter-row">
            <span>搜索</span>
            <input v-model="actorQ" class="text-input" type="search" placeholder="姓名 / 账号 / actor id" @keyup.enter="reloadActors" />
          </label>
          <label class="filter-row">
            <span>机构</span>
            <input v-model="actorOrgFilter" class="text-input" type="text" placeholder="机构编码" @keyup.enter="reloadActors" />
          </label>
          <label class="filter-row">
            <span>角色</span>
            <select v-model="actorRoleFilter" class="role-select" @change="reloadActors">
              <option value="">全部</option>
              <option v-for="rc in ASSIGNABLE_ROLES" :key="rc" :value="rc">{{ roleLabel(rc) }}</option>
            </select>
          </label>
          <label class="filter-row">
            <span>状态</span>
            <select v-model="actorStatusFilter" class="role-select" @change="reloadActors">
              <option value="">全部</option>
              <option value="active">已启用</option>
              <option value="iam_account_missing">待绑定 IAM</option>
              <option value="unmatched">未匹配</option>
              <option value="disabled">已停用</option>
            </select>
          </label>
          <button type="button" class="focus-tab refresh-btn" @click="reloadActors">刷新</button>
        </div>

        <header class="focus-section-head">
          <h2 class="focus-section-title">用户列表</h2>
          <DataSourceBadge :source="gov.actorSource.value" />
        </header>
        <p class="meta-line">{{ actorSummaryText }}</p>

        <div v-if="gov.actorError.value && gov.actorSource.value === 'fixture'" class="boot-banner boot-banner-warn">
          后端暂不可达，展示结构样例。请确认 REST 已启动且当前岗位具备 list 权限。
        </div>
        <!-- R-007：生产构建 API 失败不渲染样例，诚实提示不可用。 -->
        <div v-else-if="gov.actorSource.value === 'error'" class="boot-banner boot-banner-warn">
          数据暂不可用，请稍后重试。
        </div>

        <table v-if="actorItems.length" class="focus-table">
          <thead>
            <tr>
              <th>用户</th>
              <th>所属机构</th>
              <th>状态</th>
              <th>IAM 绑定</th>
              <th>当前角色</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="item in actorItems" :key="item.external_actor_id">
              <tr>
                <td>
                  <div class="actor-name">{{ item.display_name }}</div>
                  <code class="tech-id">{{ item.external_actor_id }}</code>
                </td>
                <td>{{ item.org_code || '—' }}</td>
                <td><span class="status-pill" :class="actorStatusTone(item.status)">{{ actorStatusLabel(item.status) }}</span></td>
                <td>{{ item.iaf_bound ? '已绑定' : '未绑定' }}</td>
                <td>
                  <template v-if="item.bindings.length">
                    <span v-for="b in item.bindings" :key="`${b.org_code}:${b.role_code}`" class="role-chip">
                      {{ roleLabel(b.role_code) }}
                      <span class="role-chip-org">@{{ b.org_code }}</span>
                      <button
                        type="button"
                        class="role-chip-revoke"
                        :disabled="!canWrite"
                        :title="canWrite ? '撤销该角色' : '样例数据下不可写'"
                        @click="onRevoke(item, b.org_code, b.role_code)"
                      >×</button>
                    </span>
                  </template>
                  <span v-else class="empty-cell">无角色</span>
                </td>
                <td class="row-actions">
                  <button type="button" class="row-link-btn" :disabled="!canWrite" @click="startAssign(item)">分派角色</button>
                  <button type="button" class="row-link-btn" :disabled="!canWrite" @click="onToggleStatus(item)">
                    {{ item.status === 'disabled' ? '启用' : '停用' }}
                  </button>
                </td>
              </tr>
              <tr v-if="assigningId === item.external_actor_id" class="detail-row">
                <td colspan="6">
                  <div class="assign-box">
                    <label class="filter-row">
                      <span>机构编码</span>
                      <input v-model="assignOrg" class="text-input" type="text" placeholder="如 SD-JNGAJ" />
                    </label>
                    <label class="filter-row">
                      <span>角色</span>
                      <select v-model="assignRoleCode" class="role-select">
                        <option value="">请选择角色</option>
                        <option v-for="rc in ASSIGNABLE_ROLES" :key="rc" :value="rc">{{ roleLabel(rc) }}</option>
                      </select>
                    </label>
                    <div class="assign-actions">
                      <button type="button" class="gov-btn gov-btn-primary" :disabled="!canWrite" @click="confirmAssign(item)">确认分派</button>
                      <button type="button" class="gov-btn gov-btn-secondary" @click="cancelAssign">取消</button>
                    </div>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
        <p v-else-if="gov.actorSource.value === 'live'" class="empty-hint">当前筛选下暂无用户（可能尚未导入存量用户）。</p>
        <p v-else-if="gov.actorSource.value === 'error'" class="empty-hint">后端不可用，暂无法加载用户列表。</p>
        <p v-else class="empty-hint">正在加载……</p>
      </div>

      <!-- ════ Tab ② 谁能访问什么 ════ -->
      <div v-show="activeTab === 'matrix'" class="tab-panel" role="tabpanel">
        <p class="disclaimer">
          只读视图：各角色当前可执行的能力（capability）清单。权威源在后端策略表，此处仅呈现，不可在本页编辑。
        </p>

        <div class="focus-tab-row">
          <button type="button" class="focus-tab refresh-btn" @click="reloadMatrix">刷新</button>
        </div>

        <header class="focus-section-head">
          <h2 class="focus-section-title">角色 → 能力矩阵</h2>
          <DataSourceBadge :source="gov.matrixSource.value" />
        </header>

        <div v-if="gov.matrixError.value && gov.matrixSource.value === 'fixture'" class="boot-banner boot-banner-warn">
          后端暂不可达，展示结构样例。请确认 REST 已启动且当前岗位具备访问权限。
        </div>
        <div v-else-if="gov.matrixSource.value === 'error'" class="boot-banner boot-banner-warn">
          数据暂不可用，请稍后重试。
        </div>

        <div v-if="matrixRoles.length" class="matrix-grid">
          <article v-for="r in matrixRoles" :key="r.role_code" class="matrix-card">
            <header class="matrix-card-head">
              <h3 class="matrix-card-title">{{ roleLabel(r.role_code) }}</h3>
              <span class="matrix-card-count">{{ r.capability_count }} 项能力</span>
            </header>
            <code class="tech-id matrix-role-code">{{ r.role_code }}</code>
            <ul class="matrix-cap-list">
              <li v-for="cap in r.capabilities" :key="cap"><code class="tech-id">{{ cap }}</code></li>
              <li v-if="!r.capabilities.length" class="empty-cell">无能力</li>
            </ul>
          </article>
        </div>
        <p v-else-if="gov.matrixSource.value === 'error'" class="empty-hint">后端不可用，暂无法加载能力矩阵。</p>
        <p v-else class="empty-hint">正在加载……</p>
      </div>

      <!-- ════ Tab ③ 旧权限映射审核（既有逻辑逐字迁入）════ -->
      <div v-show="activeTab === 'policy'" class="tab-panel" role="tabpanel">
        <p class="disclaimer">
          历史系统导入产生的旧权限映射候选，须经人工审核后才能合并写入本租户的能力策略。
          未审核前，租户策略评估仍会拒绝放行。
        </p>

        <div class="focus-tab-row">
          <label class="filter-row">
            <span>状态筛选</span>
            <select v-model="statusFilter" class="role-select" @change="reloadPolicy">
              <option value="">全部</option>
              <option value="pending_review">待审核</option>
              <option value="needs_review">需复核</option>
              <option value="approved">已批准</option>
              <option value="rejected">已驳回</option>
            </select>
          </label>
          <button type="button" class="focus-tab refresh-btn" @click="reloadPolicy">刷新</button>
        </div>

        <header class="focus-section-head">
          <h2 class="focus-section-title">映射候选列表</h2>
          <DataSourceBadge :source="panel.source.value" />
        </header>
        <p class="meta-line">{{ summaryText }}</p>

        <div v-if="panel.error.value && panel.source.value === 'fixture'" class="boot-banner boot-banner-warn">
          后端暂不可达，展示结构样例。请确认 REST 已启动且当前岗位具备 list 权限。
        </div>
        <!-- R-007：生产构建 API 失败不渲染样例，诚实提示不可用。 -->
        <div v-else-if="panel.source.value === 'error'" class="boot-banner boot-banner-warn">
          数据暂不可用，请稍后重试。
        </div>

        <table v-if="visibleItems.length" class="pkg-table">
          <thead>
            <tr>
              <th>
                <input
                  type="checkbox"
                  aria-label="全选"
                  :checked="selectedKeys.size === visibleItems.length && visibleItems.length > 0"
                  @change="toggleAll(($event.target as HTMLInputElement).checked)"
                />
              </th>
              <th>旧权限标识</th>
              <th>旧角色</th>
              <th>目标能力</th>
              <th>暴露面</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in visibleItems" :key="rowKey(item)">
              <td>
                <input
                  type="checkbox"
                  :checked="selectedKeys.has(rowKey(item))"
                  @change="toggleRow(item, ($event.target as HTMLInputElement).checked)"
                />
              </td>
              <td><span class="tech-id">{{ item.legacy_permission_ref }}</span></td>
              <td>{{ item.legacy_role_ref }}</td>
              <td><span class="tech-id">{{ item.capability_id }}</span></td>
              <td>{{ item.surface }}</td>
              <td>{{ POLICY_STATUS_LABELS[item.candidate_status] ?? item.candidate_status }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="empty-hint">当前筛选下暂无候选记录。</p>

        <div class="action-row">
          <button type="button" class="gov-btn gov-btn-secondary" :disabled="!canReview" @click="onReview('reject')">驳回所选</button>
          <button type="button" class="gov-btn gov-btn-secondary" :disabled="!canReview" @click="onReview('approve')">批准所选</button>
          <button type="button" class="gov-btn gov-btn-primary" :disabled="!canReview" @click="onReview('approve_and_apply')">
            批准并写入策略
          </button>
        </div>
      </div>
    </section>
  </main>
</template>

<style scoped>
.tab-panel {
  padding-top: 14px;
}
.disclaimer {
  font-size: 13px;
  color: #4a5568;
  line-height: 1.5;
  margin: 0 0 12px;
}
.meta-line {
  font-size: 13px;
  color: #64748b;
  margin: 0 0 12px;
}
.filter-row {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}
.text-input {
  padding: 6px 10px;
  border: 1px solid var(--b-border, #d4e2f4);
  border-radius: 6px;
  font-size: 13px;
}
.role-select {
  padding: 6px 10px;
  border: 1px solid var(--b-border, #d4e2f4);
  border-radius: 6px;
  font-size: 13px;
  background: #fff;
}
.empty-hint {
  color: #64748b;
  font-size: 14px;
}
.empty-cell {
  color: #94a3b8;
  font-size: 13px;
}
.action-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 16px;
}
.boot-banner-warn {
  background: #fff8e6;
  color: #6b4f00;
  border: 1px solid #f0c674;
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 13px;
  margin-bottom: 12px;
}

/* 用户列表 */
.actor-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--b-neutral-text, #1a1d21);
}
.row-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}
.row-link-btn {
  background: none;
  border: 0;
  padding: 0;
  color: var(--b-primary, #006be6);
  cursor: pointer;
  font-size: 13px;
  text-decoration: underline;
}
.row-link-btn:disabled {
  color: #9aa3b2;
  cursor: not-allowed;
  text-decoration: none;
}
.role-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin: 2px 6px 2px 0;
  padding: 2px 8px;
  background: var(--b-bg-subtle, #e8f2fc);
  border: 1px solid var(--b-border, #d4e2f4);
  border-radius: 999px;
  font-size: 12px;
}
.role-chip-org {
  color: #64748b;
}
.role-chip-revoke {
  border: 0;
  background: none;
  color: #b42318;
  cursor: pointer;
  font-size: 13px;
  line-height: 1;
  padding: 0 0 0 2px;
}
.role-chip-revoke:disabled {
  color: #c7cdd6;
  cursor: not-allowed;
}
.detail-row td {
  background: var(--b-bg-subtle, #f6faff);
}
.assign-box {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 20px;
  align-items: center;
  padding: 8px 0;
}
.assign-actions {
  display: flex;
  gap: 10px;
}

/* 角色 → 能力矩阵 */
.matrix-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 14px;
}
.matrix-card {
  border: 1px solid var(--b-border, #d4e2f4);
  border-radius: 8px;
  padding: 14px;
  background: #fff;
}
.matrix-card-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}
.matrix-card-title {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: var(--b-neutral-text, #1a1d21);
}
.matrix-card-count {
  font-size: 12px;
  color: #64748b;
  white-space: nowrap;
}
.matrix-role-code {
  display: inline-block;
  margin: 4px 0 8px;
  font-size: 11px;
}
.matrix-cap-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.matrix-cap-list li {
  font-size: 12px;
}

/* 旧权限映射审核表（沿用既有 pkg-table） */
.pkg-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.pkg-table th,
.pkg-table td {
  text-align: left;
  padding: 8px 10px;
  border-bottom: 1px solid var(--b-border, #e2e8f0);
}
.pkg-table th {
  color: #475569;
  font-weight: 600;
  background: var(--b-bg-subtle, #f8fafc);
}
</style>
