<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import AgentChatPanel from '@/components/AgentChatPanel.vue';
import { useAgentCatalog, type AgentInfo } from '@/composables/useAgentCatalog';
import { getProductRole } from '@/composables/useProductRole';

// 【数据应用】顶级页：基于政务共享数据构建的独立应用画廊。每个应用是一张卡片，
// 点开进入对话式工作台（经 AgentRuntime 调用平台共享数据能力）。只列 category=data-app
// 的内置 Agent（副驾类不在此列，它们嵌在各自工作流里）。可见性由 productShellNav 角色门把守。
const { agents, loading, error, load } = useAgentCatalog();
const productRole = getProductRole();

// 卡片级可用性过滤（no-permission=invisible）：只渲染当前岗位能真正调用的应用——
// 调用方角色须 ∈ 应用 allowed_roles（后端与 task 启动鉴权同口径），否则不展示卡片，
// 避免「看得到卡片、点开发问撞 403」的死胡同。allowed_roles 缺省时不过滤（向后兼容）。
// 依赖 productRole.value → 顶部岗位切换后画廊自动重算。
function roleCanUse(app: AgentInfo): boolean {
  const allowed = app.allowed_roles ?? [];
  return allowed.length === 0 || allowed.includes(productRole.value);
}
const dataApps = computed<AgentInfo[]>(() =>
  agents.value.filter((a) => a.category === 'data-app' && roleCanUse(a)),
);
const selected = ref<AgentInfo | null>(null);

function firstLine(text?: string): string {
  if (!text) return '';
  return text.split('\n').map((s) => s.trim()).filter(Boolean)[0] ?? '';
}

// 每个数据应用的快捷问题（业务化引导，降低用户冷启动成本）。
const APP_PRESETS: Record<string, string[]> = {
  'legal-person-credit-profiler': [
    '有哪些法人、登记、信用类数据可以用来研判？',
    '做企业授信尽调需要看哪些数据？',
    '招投标资格审查能用哪些信用数据？',
  ],
};
function presetsFor(id: string): string[] {
  return APP_PRESETS[id] ?? ['这个应用能做什么？', '需要用到哪些数据？', '怎么使用？'];
}

function open(app: AgentInfo) {
  selected.value = app;
}
function back() {
  selected.value = null;
}

onMounted(() => {
  void load();
});
</script>

<template>
  <main class="focus-page">
    <section class="panel panel-stack">
      <PageFocusHeader title="数据应用" meta="基于政务共享数据构建的应用与服务" />

      <!-- 应用工作台：选中某个数据应用后进入对话 -->
      <section v-if="selected" class="focus-section">
        <header class="focus-section-head app-work-head">
          <div>
            <h2 class="focus-section-title">{{ selected.name }}</h2>
            <p class="focus-prose focus-prose--muted">{{ firstLine(selected.description) }}</p>
          </div>
          <button type="button" class="app-back" @click="back">← 返回应用列表</button>
        </header>
        <div class="app-work-panel">
          <AgentChatPanel
            :key="selected.agent_id"
            :agent-id="selected.agent_id"
            :title="selected.name"
            hint="基于平台共享数据进行研判（综合多源数据，通常需 1 分钟左右）；结果仅供参考，最终认定由相应岗位拍板。"
            role-hint="部分应用需用数方管理员/审计岗位才能读取敏感字段，必要时请切换岗位。"
            placeholder="例如：我要对一家企业做信用风险尽调，有哪些数据可以研判？"
            :presets="presetsFor(selected.agent_id)"
            :allowed-role-names="selected.allowed_role_names ?? []"
            request-prefix="UI-DATAAPP"
          />
        </div>
      </section>

      <!-- 应用画廊 -->
      <section v-else class="focus-section">
        <header class="focus-section-head">
          <h2 class="focus-section-title">应用列表</h2>
        </header>

        <p v-if="loading" class="focus-prose focus-prose--muted">正在加载应用列表…</p>
        <p v-else-if="error" class="app-error">{{ error }}</p>
        <p v-else-if="!dataApps.length" class="focus-prose focus-prose--muted">暂无数据应用。</p>

        <ul v-else class="app-grid">
          <li v-for="app in dataApps" :key="app.agent_id" class="app-card">
            <h3 class="app-card-title">{{ app.name }}</h3>
            <p class="app-card-desc">{{ firstLine(app.description) }}</p>
            <footer class="app-card-foot">
              <span class="app-card-tag">由政务共享数据驱动</span>
              <button type="button" class="app-open" @click="open(app)">打开</button>
            </footer>
          </li>
        </ul>
      </section>
    </section>
  </main>
</template>

<style scoped>
.app-grid {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}
.app-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 16px;
  border: 1px solid #d4e2f4;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 2px 10px rgba(15, 35, 70, 0.06);
}
.app-card-title {
  margin: 0;
  font-size: 15px;
  color: #0f3d7a;
}
.app-card-desc {
  margin: 0;
  flex: 1;
  font-size: 13px;
  line-height: 1.5;
  color: #4a5b6d;
}
.app-card-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.app-card-tag {
  font-size: 11px;
  color: #5a6b7d;
  background: #f0f6ff;
  border-radius: 999px;
  padding: 3px 10px;
}
.app-open {
  padding: 6px 16px;
  border: none;
  border-radius: 8px;
  background: #006be6;
  color: #fff;
  cursor: pointer;
  font-size: 13px;
}
.app-work-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.app-back {
  border: 1px solid #d4e2f4;
  background: #f4f9ff;
  border-radius: 8px;
  padding: 6px 12px;
  cursor: pointer;
  font-size: 13px;
  color: #0048a8;
  white-space: nowrap;
}
.app-work-panel {
  margin-top: 12px;
  min-height: 420px;
  border: 1px solid #e2ebf6;
  border-radius: 12px;
  padding: 14px;
  background: #fff;
}
.app-error {
  margin: 0;
  font-size: 13px;
  color: #b42318;
}
</style>
