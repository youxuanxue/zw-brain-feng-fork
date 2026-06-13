<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import DataSourceBadge from '@/components/DataSourceBadge.vue';
import { usePolicyCandidates } from '@/composables/usePolicyCandidates';
import type { PolicyCandidateItem } from '@/fixtures/b12-iam-fixture';
import { pushToast } from '@/composables/useActionStub';
import { getProductRole } from '@/composables/useProductRole';

const role = getProductRole();
const panel = usePolicyCandidates();

const statusFilter = ref('');
const selectedKeys = ref<Set<string>>(new Set());

const STATUS_LABELS: Record<string, string> = {
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
    ([k, n]) => `${STATUS_LABELS[k] ?? k} ${n}`
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

async function reload(): Promise<void> {
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
    await reload();
  } else {
    pushToast({ kind: 'error', title: '审核失败', detail: r.error ?? '后端报错' });
  }
}

onMounted(() => {
  void reload();
});
</script>

<template>
  <main class="focus-page">
    <section class="panel panel-stack">
      <PageFocusHeader title="身份治理" meta="旧权限映射候选 · 人工审核 · 租户策略" />

      <p class="disclaimer">
        历史系统导入产生的旧权限映射候选，须经人工审核后才能合并写入本租户的能力策略。
        未审核前，租户策略评估仍会拒绝放行。
      </p>

      <div class="focus-tab-row">
        <label class="filter-row">
          <span>状态筛选</span>
          <select v-model="statusFilter" class="role-select" @change="reload">
            <option value="">全部</option>
            <option value="pending_review">待审核</option>
            <option value="needs_review">需复核</option>
            <option value="approved">已批准</option>
            <option value="rejected">已驳回</option>
          </select>
        </label>
        <button type="button" class="focus-tab refresh-btn" @click="reload">刷新</button>
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
            <td>{{ STATUS_LABELS[item.candidate_status] ?? item.candidate_status }}</td>
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
    </section>
  </main>
</template>

<style scoped>
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
.empty-hint {
  color: #64748b;
  font-size: 14px;
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
</style>
