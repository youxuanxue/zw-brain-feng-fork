<script setup lang="ts">
import { computed } from 'vue';
import { useWorkbench } from '@/composables/useWorkbench';
import { formatTodoStatus, todoStatusTone } from '@/lib/statusLabels';

const { data, source, error, refresh } = useWorkbench();

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
        {{ data.greeting }}，<span class="p1-count">{{ todoCount }}</span> 项待办
        <span v-if="urgentCount" class="p1-urgent">（{{ urgentCount }} 项需尽快处理）</span>
      </h1>
    </header>
    <p v-else-if="source === 'loading'" class="focus-empty">正在加载工作台……</p>

    <div v-if="source === 'fixture'" class="panel p1-warn">
      未连接后端：{{ error }}
      <button type="button" @click="refresh">重试</button>
    </div>

    <div v-if="data" class="p1-layout">
      <section class="panel p1-card">
        <h2 class="p1-block-title">今日待办</h2>
        <ul class="p1-list p1-list--todo">
          <li v-for="(todo, idx) in data.todos" :key="`${todo.id}-${idx}`" class="p1-row">
            <div class="p1-row-main">
              <a v-if="todo.href" :href="todo.href" class="p1-row-title">{{ todo.title }}</a>
              <span v-else class="p1-row-title">{{ todo.title }}</span>
            </div>
            <span class="p1-status" :class="todoStatusTone(String(todo.status))">
              {{ formatTodoStatus(String(todo.status)) }}
            </span>
          </li>
        </ul>
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

      <section v-if="data.highlights.length" class="panel p1-card p1-card--span">
        <h2 class="p1-block-title">本周亮点</h2>
        <ul class="p1-list p1-list--bullets">
          <li v-for="(h, i) in data.highlights" :key="i" class="p1-row p1-row--bullet">{{ h }}</li>
        </ul>
      </section>
    </div>
  </main>
</template>

<style scoped>
.p1-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
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
  gap: 16px;
  align-items: start;
}
.p1-card--span {
  grid-column: 1 / 2;
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
.p1-list--bullets {
  list-style: disc;
  padding-left: 1.25rem;
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
.p1-row--bullet {
  display: list-item;
  padding: 8px 0;
  border-bottom: 0;
  font-size: 14px;
  line-height: 1.6;
  color: var(--b-neutral-text, #1a1d21);
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
