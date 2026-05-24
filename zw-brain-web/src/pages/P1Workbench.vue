<script setup lang="ts">
import { computed } from 'vue';
import { useWorkbench } from '@/composables/useWorkbench';

const { data, source, error, refresh } = useWorkbench('ROLE_ORGAN_OPERATER');

const todoCount = computed(() => data.value?.todos.length ?? 0);
const urgentCount = computed(
  () =>
    data.value?.todos.filter((t) =>
      /待|审批|补录|核查|确认|处理中|预警|告警|拦截|异常|修改/.test(String(t.status))
    ).length ?? 0
);
</script>

<template>
  <main class="p1">
    <header class="p1-hero">
      <div class="p1-hero-tag">P1 · 工作台</div>
      <h1 v-if="data" class="p1-hero-title">
        {{ data.greeting }}，今天有 <span class="p1-count">{{ todoCount }}</span> 项待办。
      </h1>
      <p v-if="data" class="p1-hero-sub">
        其中 <strong>{{ urgentCount }} 项</strong> 需要你立即处理 · 关键动作均保留人工确认与审计回执
      </p>
      <p v-else-if="source === 'loading'" class="p1-hero-sub">正在加载……</p>
    </header>

    <div v-if="source === 'fixture'" class="p1-banner">
      <strong>开发期数据回退：</strong>
      未连接到 brain 后端（/api/skills/workbench.view 失败：{{ error }}）。
      当前显示的是仓内 sd-default 种子切片（zw_brain/domain/seed_snapshot.json）。
      <button type="button" @click="refresh">重试</button>
    </div>
    <div v-else-if="source === 'live'" class="p1-banner p1-banner-ok">
      <strong>已连接 brain：</strong>数据来自 /api/skills/workbench.view（sd-default 真实数据）。
    </div>

    <div v-if="data" class="p1-grid">
      <section class="p1-card p1-card-wide">
        <header class="p1-card-head">
          <h2>今日待办</h2>
          <p>按重要程度分组</p>
        </header>
        <ul class="todo-list">
          <li v-for="todo in data.todos" :key="todo.id" class="todo-item">
            <div class="todo-main">
              <a v-if="todo.href" :href="todo.href" class="todo-title">{{ todo.title }}</a>
              <span v-else class="todo-title">{{ todo.title }}</span>
              <div class="todo-meta">{{ todo.id }}</div>
            </div>
            <span class="todo-status">{{ todo.status }}</span>
          </li>
        </ul>
      </section>

      <aside class="p1-card">
        <header class="p1-card-head">
          <h2>办理建议</h2>
          <p>仅供参考</p>
        </header>
        <p class="ai-summary">{{ data.aiSummary.summary }}</p>
        <details v-if="data.aiSummary.basis?.length" class="ai-basis">
          <summary>查看依据</summary>
          <ul>
            <li v-for="(b, i) in data.aiSummary.basis" :key="i">{{ b }}</li>
          </ul>
        </details>
      </aside>

      <section class="p1-card p1-card-wide">
        <header class="p1-card-head">
          <h2>本周亮点</h2>
          <p>来自真实政务案例</p>
        </header>
        <ul class="highlight-list">
          <li v-for="(h, i) in data.highlights" :key="i">{{ h }}</li>
        </ul>
      </section>
    </div>
  </main>
</template>

<style scoped>
.p1 {
  display: grid;
  gap: 20px;
}
.p1-hero {
  border: 1px solid var(--b-border);
  border-radius: 12px;
  padding: 20px;
  background: linear-gradient(180deg, #ffffff 0%, #f7fbff 100%);
}
.p1-hero-tag {
  display: inline-block;
  font-size: 12px;
  padding: 2px 10px;
  background: var(--b-primary);
  color: #fff;
  border-radius: 999px;
  margin-bottom: 8px;
}
.p1-hero-title {
  font-size: 24px;
  margin: 0 0 6px;
  color: var(--b-neutral-text);
}
.p1-hero-sub {
  font-size: 14px;
  color: var(--b-muted);
  margin: 0;
}
.p1-count {
  color: var(--b-primary);
  font-size: 28px;
  margin: 0 4px;
}
.p1-banner {
  border: 1px solid #f0c674;
  background: #fff8e6;
  color: #6b4f00;
  padding: 12px 16px;
  border-radius: 8px;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 12px;
}
.p1-banner-ok {
  border-color: #9ad29a;
  background: #effaee;
  color: #1f5e1f;
}
.p1-banner button {
  margin-left: auto;
  padding: 4px 10px;
  border: 1px solid currentColor;
  background: transparent;
  border-radius: 6px;
  cursor: pointer;
  color: inherit;
  font-size: 13px;
}
.p1-grid {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 16px;
}
.p1-card {
  background: var(--b-bg-card);
  border: 1px solid var(--b-border);
  border-radius: 12px;
  padding: 20px;
}
.p1-card-wide {
  grid-column: 1 / 2;
}
.p1-card-head h2 {
  font-size: 18px;
  margin: 0;
}
.p1-card-head p {
  margin: 4px 0 12px;
  font-size: 13px;
  color: var(--b-muted);
}
.todo-list,
.highlight-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.todo-item {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 12px 0;
  border-bottom: 1px solid var(--b-border);
  gap: 16px;
}
.todo-item:last-child {
  border-bottom: 0;
}
.todo-title {
  font-weight: 600;
  color: var(--b-neutral-text);
  text-decoration: none;
}
.todo-title:hover {
  color: var(--b-primary);
}
.todo-meta {
  font-size: 12px;
  color: var(--b-muted);
  margin-top: 4px;
}
.todo-status {
  flex-shrink: 0;
  padding: 4px 10px;
  background: var(--b-bg-subtle);
  border-radius: 999px;
  font-size: 12px;
  color: var(--b-primary);
}
.highlight-list li {
  padding: 8px 0;
  font-size: 14px;
  color: var(--b-neutral-text);
  border-bottom: 1px dashed var(--b-border);
}
.highlight-list li:last-child {
  border-bottom: 0;
}
.ai-summary {
  font-size: 15px;
  line-height: 1.7;
  color: var(--b-neutral-text);
}
.ai-basis {
  margin-top: 12px;
  font-size: 13px;
  color: var(--b-muted);
}
.ai-basis ul {
  margin: 6px 0 0;
  padding-left: 20px;
}
</style>
