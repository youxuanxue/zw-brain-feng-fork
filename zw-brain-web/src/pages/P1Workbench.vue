<script setup lang="ts">
import { computed } from 'vue';
import { useWorkbench } from '@/composables/useWorkbench';
import { formatTodoStatus, todoStatusTone } from '@/lib/statusLabels';
import { humanizeTitle } from '@/lib/userLanguage';
import { getProductRole } from '@/composables/useProductRole';
import {
  canPlatformReviewRequests,
  canReviewRequests,
  isPlatformOps,
  isReadonlySupervisor,
} from '@/lib/requestFlowRoles';

// 缺陷 2（业务方试用反馈）：业务运营员待办「不对路」。机制单源 = 后端 workbench_backlog_projection
// （真实库现算、每条带深链，第二组）；角色 → 待办语义（白话类目，第四组）已下沉到该
// 后端投影（语义定义见 docs/decisions/role-projection-views-business-review-package.md），
// 前端只渲染、不自算（避免两套口径漂移）。
const { data, source, error, refresh } = useWorkbench();
const role = getProductRole();

// 工作台语境按岗位职责四分（D57②/R8，修正原「非审核岗即申请人」二分把安全审计员/
// 平台运维员误归申请人「我的申请进度」的错配）：
//   applicant  部门操作员 —— 申请进度（P12 / 0609 docx：不显待办、换申请进度）
//   reviewer   部门管理员 / 业务运营员 —— 今日待办（审批/受理岗）
//   supervisor 安全审计员 —— 监督概览（已签纯只读口径：无写待办，指引去查审计）
//   ops        平台运维员 —— 运维核查
const contextVariant = computed(() => {
  if (isReadonlySupervisor(role.value)) return 'supervisor' as const;
  if (isPlatformOps(role.value)) return 'ops' as const;
  if (!canReviewRequests(role.value) && !canPlatformReviewRequests(role.value)) {
    return 'applicant' as const;
  }
  return 'reviewer' as const;
});
const itemNoun = computed(() => (contextVariant.value === 'applicant' ? '进度' : '待办'));
const blockTitle = computed(
  () =>
    ({
      applicant: '我的申请进度',
      reviewer: '今日待办',
      supervisor: '监督概览',
      ops: '运维核查',
    })[contextVariant.value],
);
const emptyText = computed(
  () =>
    ({
      applicant: '暂无进行中的申请。',
      reviewer: '当前岗位暂无待办事项。',
      supervisor: '安全审计员为纯只读监督岗，无办理待办；审计动态请前往「查审计」。',
      ops: '当前没有运维核查事项。',
    })[contextVariant.value],
);

const todoCount = computed(() => data.value?.todos.length ?? 0);
const urgentCount = computed(
  () =>
    data.value?.todos.filter((t) =>
      /待|审批|补录|核查|确认|处理中|预警|告警|拦截|异常|修改|补正|交付/.test(
        formatTodoStatus(String(t.status))
      )
    ).length ?? 0
);
</script>

<template>
  <main class="focus-page p1-page">
    <header v-if="data" class="panel p1-hero">
      <h1 class="p1-hero-title">
        {{ data.greeting }}，<span class="p1-count">{{ todoCount }}</span> 项{{ itemNoun }}
        <span v-if="urgentCount" class="p1-urgent">（{{ urgentCount }} 项需尽快处理）</span>
      </h1>
    </header>
    <p v-else-if="source === 'loading'" class="focus-empty">正在加载工作台……</p>
    <!-- R-007：生产构建后端故障时不渲染 fixture 假待办，诚实提示不可用 + 重试。 -->
    <div v-else-if="source === 'error'" class="panel p1-warn">
      工作台数据暂不可用，请稍后重试。
      <button type="button" @click="refresh">重试</button>
    </div>

    <div v-if="source === 'fixture'" class="panel p1-warn">
      未连接后端：{{ error }}
      <button type="button" @click="refresh">重试</button>
    </div>

    <div v-if="data" class="p1-layout">
      <section class="panel p1-card">
        <h2 class="p1-block-title">{{ blockTitle }}</h2>
        <ul v-if="data.todos.length" class="p1-list p1-list--todo">
          <li
            v-for="(todo, idx) in data.todos"
            :key="`${todo.id}-${idx}`"
            class="p1-row"
            data-testid="workbench-todo"
          >
            <div class="p1-row-main">
              <a
                v-if="todo.href"
                :href="todo.href"
                class="p1-row-title"
                data-testid="workbench-todo-link"
                >{{ humanizeTitle(todo.title) }}</a
              >
              <span v-else class="p1-row-title">{{ humanizeTitle(todo.title) }}</span>
            </div>
            <span class="p1-status" :class="todoStatusTone(String(todo.status))">
              {{ formatTodoStatus(String(todo.status)) }}
            </span>
          </li>
        </ul>
        <p v-else class="p1-empty">{{ emptyText }}</p>
      </section>

      <aside class="panel p1-side">
        <h2 class="p1-block-title">办理建议</h2>
        <p class="p1-prose">{{ data.aiSummary.summary }}</p>
        <details v-if="data.aiSummary.basis?.length" class="p1-basis">
          <summary>查看依据</summary>
          <ul>
            <li v-for="(b, i) in data.aiSummary.basis" :key="i">{{ b }}</li>
          </ul>
        </details>
      </aside>
    </div>
  </main>
</template>

<style scoped>
.p1-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.p1-hero {
  background: linear-gradient(180deg, #f4f9ff 0%, #ffffff 100%);
}
.p1-hero-title {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  line-height: 1.5;
  color: var(--b-neutral-text, #1a1d21);
}
.p1-count {
  color: var(--b-primary, #006be6);
}
.p1-urgent {
  font-size: 14px;
  font-weight: 500;
  color: var(--b-muted, #5c6370);
}
.p1-warn {
  border-color: #f0c674 !important;
  background: #fff8e6 !important;
  color: #6b4f00;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 12px;
}
.p1-warn button {
  margin-left: auto;
  padding: 4px 10px;
  border: 1px solid currentColor;
  background: transparent;
  border-radius: 6px;
  cursor: pointer;
}
.p1-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.65fr) minmax(300px, 1fr);
  gap: 20px;
  align-items: start;
}
.p1-side {
  grid-column: 2 / 3;
  grid-row: 1 / span 2;
}
.p1-block-title {
  margin: 0 0 14px;
  padding: 0;
  font-size: 16px;
  font-weight: 700;
  line-height: 1.35;
  color: var(--b-neutral-text, #1a1d21);
}
.p1-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.p1-empty {
  margin: 0;
  font-size: 14px;
  color: var(--b-muted, #5c6370);
}
.p1-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 0;
  margin: 0;
  border-bottom: 1px solid var(--b-border, #d4e2f4);
}
.p1-row:first-child {
  padding-top: 2px;
}
.p1-row:last-child {
  border-bottom: 0;
  padding-bottom: 2px;
}
.p1-row-main {
  flex: 1;
  min-width: 0;
}
.p1-row-title {
  display: block;
  font-weight: 600;
  font-size: 14px;
  line-height: 1.55;
  color: var(--b-neutral-text, #1a1d21);
  text-decoration: none;
  word-break: break-word;
}
.p1-row-title:hover {
  color: var(--b-primary, #006be6);
}
.p1-status {
  flex-shrink: 0;
  padding: 5px 12px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.2;
  white-space: nowrap;
}
.p1-status.tone-warn {
  background: #fff3cd;
  color: #856404;
}
.p1-status.tone-ok {
  background: #d4f8e0;
  color: #155724;
}
.p1-status.tone-info {
  background: var(--b-bg-subtle, #e8f2fc);
  color: var(--b-primary, #006be6);
}
.p1-status.tone-danger {
  background: #f8d7da;
  color: #842029;
}
.p1-status.tone-neutral {
  background: var(--b-bg-subtle, #e8f2fc);
  color: var(--b-muted, #5c6370);
}
.p1-prose {
  margin: 0;
  font-size: 14px;
  line-height: 1.75;
  color: var(--b-neutral-text, #1a1d21);
  word-break: break-word;
}
.p1-basis {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--b-border, #d4e2f4);
  font-size: 13px;
  color: var(--b-muted, #5c6370);
}
.p1-basis summary {
  cursor: pointer;
  font-weight: 600;
  color: var(--b-primary, #006be6);
}
.p1-basis ul {
  margin: 10px 0 0;
  padding-left: 1.1rem;
  line-height: 1.65;
}
@media (max-width: 960px) {
  .p1-layout {
    grid-template-columns: 1fr;
  }
  .p1-side {
    grid-column: 1;
    grid-row: auto;
  }
}
</style>
