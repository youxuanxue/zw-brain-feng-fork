<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import PageFocusHeader from '@/components/PageFocusHeader.vue';
import AgentChatPanel from '@/components/AgentChatPanel.vue';
import { useAgentCatalog, type AgentInfo } from '@/composables/useAgentCatalog';
import { authFetch, PRODUCT_ROLE_LABELS } from '@/composables/useAuth';
import { apiUrl } from '@/composables/useApiBase';
import { getProductRole } from '@/composables/useProductRole';
import { pushToast } from '@/composables/useActionStub';
import { hasRole } from '@/lib/pageAccess';
import { defaultAgentAuthorizationRoles } from '@/lib/requestFlowRoles';

// 【智能体】顶级页：业务岗位看本岗位助手；平台运维员看全部助手和状态。
const { agents, loading, error, load, updateAgentState, reloadAgentRuntime } = useAgentCatalog();
const productRole = getProductRole();
const selected = ref<AgentInfo | null>(null);
const activeClass = ref<'A' | 'B'>('A');
const serviceReady = ref<boolean | null>(null);
const serviceError = ref<string | null>(null);
const opsBusyAgentId = ref<string | null>(null);
const opsMessage = ref<string | null>(null);
const expandedAuthorizationAgentIds = ref<Set<string>>(new Set());

const isOpsRole = computed(() => hasRole(productRole.value, 'ROLE_SYSTEM'));

function isAgentEnabled(agent: AgentInfo): boolean {
  return agent.enabled !== false && agent.state?.enabled !== false;
}

function callerCanUseAgent(agent: AgentInfo): boolean {
  return agent.callable === true && isAgentEnabled(agent) && agent.runtime_ready !== false && serviceReady.value === true;
}

function roleCanSee(agent: AgentInfo): boolean {
  return isOpsRole.value || callerCanUseAgent(agent);
}

const scenarioAgents = computed<AgentInfo[]>(() =>
  agents.value
    .filter((a) => (a.category === 'agent' || a.category === 'data-app') && roleCanSee(a))
    .sort((a, b) => `${a.agent_class ?? ''}${a.name ?? ''}`.localeCompare(`${b.agent_class ?? ''}${b.name ?? ''}`, 'zh-Hans-CN')),
);

const classCounts = computed(() => ({
  A: scenarioAgents.value.filter((a) => (a.agent_class ?? 'A') === 'A').length,
  B: scenarioAgents.value.filter((a) => a.agent_class === 'B').length,
}));

const visibleAgents = computed<AgentInfo[]>(() =>
  scenarioAgents.value.filter((a) => (a.agent_class ?? 'A') === activeClass.value),
);

function firstLine(text?: string): string {
  if (!text) return '';
  return text.split('\n').map((s) => s.trim()).filter(Boolean)[0] ?? '';
}

const AGENT_PRESETS: Record<string, string[]> = {
  'a-zw-search-helper': [
    '我想找企业登记和纳税相关数据，哪些资源可申请？',
    '停车场一张图需要哪些目录资源？',
    '没有精确资源时我该怎么描述需求？',
  ],
  'a-data-journey-copilot': [
    '帮我梳理当前申请和交付进度。',
    '申请被退回后下一步该看哪些信息？',
    '我拿到凭据前还缺哪些环节？',
  ],
  'b-legal-person-credit-profiler': [
    '做企业授信尽调需要看哪些数据？',
    '招投标资格审查能用哪些信用数据？',
    '法人信用画像里哪些字段不能直接下结论？',
  ],
  'a-audit-investigation-copilot': [
    '最近有哪些异常审计线索？',
    '帮我汇总一次拒绝访问的追责线索。',
    '审计摘要需要哪些证据支撑？',
  ],
};

function presetsFor(agent: AgentInfo): string[] {
  if (Array.isArray(agent.quick_questions) && agent.quick_questions.length >= 3) {
    return agent.quick_questions.slice(0, 3);
  }
  return AGENT_PRESETS[agent.agent_id] ?? [
    '这个智能体适合处理什么问题？',
    '我应该提供哪些编号或条件？',
    '请给出一个只读研判摘要。',
  ];
}

function classLabel(agent: AgentInfo): string {
  return agent.agent_class === 'B' ? 'B 类 · 用数助手' : 'A 类 · 办事助手';
}

function agentDisplayName(agent: AgentInfo): string {
  return agent.name ?? agent.agent_id;
}

function statusText(agent: AgentInfo): string {
  if (!isAgentEnabled(agent)) return isOpsRole.value ? '已停用' : '暂不可用';
  if (agent.runtime_ready === false) return isOpsRole.value ? '未配置' : '暂不可用';
  if (serviceReady.value === null) return '检查中';
  if (serviceReady.value !== true) return isOpsRole.value ? '服务未启动' : '暂不可用';
  if (agent.callable !== true) return '暂不可用';
  return isOpsRole.value ? '运行正常' : '';
}

function canOpenAgent(agent: AgentInfo): boolean {
  return callerCanUseAgent(agent);
}

function actionText(agent: AgentInfo): string {
  if (canOpenAgent(agent)) return '打开';
  if (!isAgentEnabled(agent)) return isOpsRole.value ? '已停用' : '暂不可用';
  if (agent.runtime_ready === false) return isOpsRole.value ? '未配置' : '暂不可用';
  if (serviceReady.value === null) return '检查中';
  if (serviceReady.value !== true) return isOpsRole.value ? '服务未启动' : '暂不可用';
  return '暂不可用';
}

function open(agent: AgentInfo) {
  if (!canOpenAgent(agent)) return;
  selected.value = agent;
}

function back() {
  selected.value = null;
}

function roleLabel(agent: AgentInfo, role: string): string {
  const roles = agent.assignable_roles ?? [];
  const idx = roles.indexOf(role);
  return agent.assignable_role_names?.[idx] ?? PRODUCT_ROLE_LABELS[role] ?? role;
}

function configuredRoleNames(agent: AgentInfo): string[] {
  return configuredRoles(agent).map((role) => roleLabel(agent, role));
}

function authorizationSummary(agent: AgentInfo): string {
  const names = configuredRoleNames(agent);
  if (!names.length) return '未授权岗位';
  if (names.length <= 3) return names.join(' / ');
  return `${names.slice(0, 3).join(' / ')} 等 ${names.length} 个岗位`;
}

function assignableRoles(agent: AgentInfo): string[] {
  return agent.assignable_roles ?? defaultAgentAuthorizationRoles();
}

function configuredRoles(agent: AgentInfo): string[] {
  return agent.allowed_roles ?? agent.state?.allowed_roles ?? [];
}

function isRoleChecked(agent: AgentInfo, role: string): boolean {
  return configuredRoles(agent).includes(role);
}

function isOpsBusy(agent: AgentInfo): boolean {
  return opsBusyAgentId.value === agent.agent_id;
}

function isAuthorizationExpanded(agent: AgentInfo): boolean {
  return expandedAuthorizationAgentIds.value.has(agent.agent_id);
}

function toggleAuthorization(agent: AgentInfo): void {
  const next = new Set(expandedAuthorizationAgentIds.value);
  if (next.has(agent.agent_id)) next.delete(agent.agent_id);
  else next.add(agent.agent_id);
  expandedAuthorizationAgentIds.value = next;
}

async function persistAgentState(agent: AgentInfo, enabled: boolean, allowedRoles: string[], reason: string): Promise<void> {
  opsBusyAgentId.value = agent.agent_id;
  try {
    await updateAgentState(agent.agent_id, { enabled, allowed_roles: allowedRoles, reason });
    await load();
    pushToast({ kind: 'ok', title: '已更新', detail: `${agentDisplayName(agent)} 已保存。` });
  } catch (e) {
    pushToast({
      kind: 'error',
      title: '更新失败',
      detail: e instanceof Error ? e.message : '请稍后重试。',
    });
  } finally {
    opsBusyAgentId.value = null;
  }
}

async function setAgentEnabled(agent: AgentInfo, enabled: boolean): Promise<void> {
  await persistAgentState(
    agent,
    enabled,
    configuredRoles(agent),
    enabled ? '平台运维员启用智能体' : '平台运维员停用智能体',
  );
}

async function toggleAgentRole(agent: AgentInfo, role: string, checked: boolean): Promise<void> {
  const next = new Set(configuredRoles(agent));
  if (checked) next.add(role);
  else next.delete(role);
  await persistAgentState(agent, isAgentEnabled(agent), Array.from(next), '平台运维员调整授权岗位');
}

function toggleAgentRoleFromEvent(agent: AgentInfo, role: string, event: Event): void {
  const target = event.target as HTMLInputElement | null;
  void toggleAgentRole(agent, role, Boolean(target?.checked));
}

async function reloadRuntime(): Promise<void> {
  opsMessage.value = '正在重载智能体...';
  try {
    await reloadAgentRuntime();
    await Promise.all([load(), loadServiceReady()]);
    opsMessage.value = '已重载智能体，新任务会使用最新配置。';
    pushToast({
      kind: 'ok',
      title: '已重载',
      detail: opsMessage.value,
    });
  } catch (e) {
    opsMessage.value = '智能体重载失败。';
    pushToast({ kind: 'error', title: '重载失败', detail: e instanceof Error ? e.message : '请稍后重试。' });
  }
}

async function loadServiceReady(): Promise<void> {
  serviceError.value = null;
  try {
    const resp = await authFetch(apiUrl('/health'));
    if (!resp.ok) throw new Error();
    const body = (await resp.json()) as { agent_runtime?: { ready?: boolean; status?: string } };
    serviceReady.value = body.agent_runtime?.ready === true || body.agent_runtime?.status === 'running';
  } catch {
    serviceReady.value = false;
    serviceError.value = null;
  }
}

onMounted(() => {
  void Promise.all([load(), loadServiceReady()]);
});

watch(productRole, () => {
  selected.value = null;
  void load();
});

watch([scenarioAgents, productRole, serviceReady], () => {
  if (selected.value && !scenarioAgents.value.some((agent) => agent.agent_id === selected.value?.agent_id)) {
    selected.value = null;
  }
});
</script>

<template>
  <main class="focus-page">
    <section class="panel panel-stack">
      <PageFocusHeader title="智能体" meta="常用问题交给助手，关键动作仍由岗位人员确认" />

      <section v-if="selected" class="focus-section">
        <header class="focus-section-head agent-work-head">
          <div>
            <div class="agent-kicker">
              <span class="agent-type">{{ classLabel(selected) }}</span>
              <span v-if="isOpsRole" class="agent-chip">{{ statusText(selected) }}</span>
            </div>
            <h2 class="focus-section-title">{{ agentDisplayName(selected) }}</h2>
            <p class="focus-prose focus-prose--muted">{{ firstLine(selected.description) }}</p>
          </div>
          <button type="button" class="agent-back" @click="back">返回列表</button>
        </header>

        <div class="agent-work-panel">
          <AgentChatPanel
            :key="selected.agent_id"
            :agent-id="selected.agent_id"
            :title="agentDisplayName(selected)"
            hint="只看当前岗位可见信息；给建议，不代办。"
            placeholder="输入你的问题、编号或判断条件。"
            :presets="presetsFor(selected)"
            :allowed-role-names="selected.allowed_role_names ?? []"
            :runtime-enabled="canOpenAgent(selected)"
            request-prefix="UI-AGENT"
          />
        </div>
      </section>

      <section v-else class="focus-section">
        <header class="focus-section-head agent-list-head">
          <div>
            <h2 class="focus-section-title">智能体列表</h2>
            <p class="focus-prose focus-prose--muted">
              {{ isOpsRole ? '平台运维员可查看全部智能体，处理启停、授权和重载。' : '这里只显示当前岗位现在可用的助手。' }}
            </p>
          </div>
          <div class="agent-list-actions">
            <div v-if="isOpsRole" class="agent-ops-toolbar" aria-label="平台运维操作">
              <button
                type="button"
                class="agent-tool"
                title="让智能体服务重新读取配置"
                @click="reloadRuntime"
              >
                重载
              </button>
            </div>
            <div class="agent-tabs" role="tablist" aria-label="智能体分类">
              <button
                type="button"
                class="agent-tab"
                :class="{ active: activeClass === 'A' }"
                role="tab"
                :aria-selected="activeClass === 'A'"
                @click="activeClass = 'A'"
              >
                A 类办事助手 <span>{{ classCounts.A }}</span>
              </button>
              <button
                type="button"
                class="agent-tab"
                :class="{ active: activeClass === 'B' }"
                role="tab"
                :aria-selected="activeClass === 'B'"
                @click="activeClass = 'B'"
              >
                B 类用数助手 <span>{{ classCounts.B }}</span>
              </button>
            </div>
          </div>
        </header>
        <p v-if="isOpsRole && opsMessage" class="agent-ops-message">{{ opsMessage }}</p>

        <p v-if="loading" class="focus-prose focus-prose--muted">正在加载智能体列表...</p>
        <p v-else-if="error || serviceError" class="agent-error">{{ error || serviceError }}</p>
        <p v-else-if="!scenarioAgents.length" class="focus-prose focus-prose--muted">当前岗位暂无可用助手。</p>
        <p v-else-if="!visibleAgents.length" class="focus-prose focus-prose--muted">当前岗位暂无此类助手。</p>

        <ul v-else class="agent-grid">
          <li v-for="agent in visibleAgents" :key="agent.agent_id" class="agent-card">
            <div class="agent-card-head">
              <span class="agent-type">{{ classLabel(agent) }}</span>
              <span v-if="isOpsRole" class="agent-chip">{{ statusText(agent) }}</span>
            </div>
            <h3 class="agent-card-title">{{ agentDisplayName(agent) }}</h3>
            <p class="agent-card-desc">{{ firstLine(agent.description) }}</p>
            <div v-if="isOpsRole" class="agent-ops">
              <div class="agent-ops-row">
                <span class="agent-ops-label">操作</span>
                <button
                  type="button"
                  class="agent-toggle"
                  :class="{ active: isAgentEnabled(agent) }"
                  :disabled="isOpsBusy(agent)"
                  @click="setAgentEnabled(agent, !isAgentEnabled(agent))"
                >
                  {{ isAgentEnabled(agent) ? '停用' : '启用' }}
                </button>
              </div>
              <div class="agent-ops-row">
                <span class="agent-ops-label">授权</span>
                <span class="agent-auth-summary">{{ authorizationSummary(agent) }}</span>
                <button
                  v-if="assignableRoles(agent).length"
                  type="button"
                  class="agent-auth-toggle"
                  :aria-expanded="isAuthorizationExpanded(agent)"
                  @click="toggleAuthorization(agent)"
                >
                  {{ isAuthorizationExpanded(agent) ? '收起' : '调整授权' }}
                </button>
              </div>
              <div v-if="isAuthorizationExpanded(agent)" class="agent-ops-row agent-ops-roles">
                <label
                  v-for="role in assignableRoles(agent)"
                  :key="`${agent.agent_id}-${role}`"
                  class="agent-role-option"
                >
                  <input
                    type="checkbox"
                    :checked="isRoleChecked(agent, role)"
                    :disabled="isOpsBusy(agent)"
                    @change="toggleAgentRoleFromEvent(agent, role, $event)"
                  />
                  <span>{{ roleLabel(agent, role) }}</span>
                </label>
              </div>
            </div>
            <footer class="agent-card-foot">
              <button
                type="button"
                class="agent-open"
                :disabled="!canOpenAgent(agent)"
                :aria-disabled="!canOpenAgent(agent)"
                @click="open(agent)"
              >
                {{ actionText(agent) }}
              </button>
            </footer>
          </li>
        </ul>
      </section>
    </section>
  </main>
</template>

<style scoped>
.agent-list-head,
.agent-work-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}
.agent-list-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
}
.agent-ops-toolbar {
  display: inline-flex;
  gap: 6px;
}
.agent-tabs {
  display: inline-flex;
  gap: 4px;
  padding: 3px;
  border: 1px solid #cdd8e6;
  border-radius: 8px;
  background: #f6f8fb;
  flex-shrink: 0;
}
.agent-tab {
  border: 0;
  border-radius: 6px;
  padding: 7px 10px;
  background: transparent;
  color: #41566f;
  cursor: pointer;
  font-size: 13px;
  white-space: nowrap;
}
.agent-tab span {
  margin-left: 4px;
  color: #6b7c8f;
}
.agent-tab.active {
  background: #fff;
  color: #0f3d7a;
  box-shadow: 0 1px 4px rgba(15, 35, 70, 0.12);
}
.agent-tool,
.agent-toggle {
  min-height: 30px;
  border: 1px solid #cdd8e6;
  border-radius: 8px;
  background: #fff;
  color: #17324d;
  cursor: pointer;
  font-size: 13px;
}
.agent-tool {
  padding: 5px 12px;
}
.agent-toggle {
  min-width: 64px;
  padding: 4px 10px;
}
.agent-auth-toggle {
  min-height: 28px;
  border: 1px solid #cdd8e6;
  border-radius: 8px;
  background: #fff;
  color: #0f3d7a;
  cursor: pointer;
  font-size: 12px;
  padding: 3px 8px;
}
.agent-toggle.active {
  color: #7a2e0e;
  border-color: #efc0a6;
  background: #fff6ef;
}
.agent-tool:disabled,
.agent-toggle:disabled,
.agent-auth-toggle:disabled,
.agent-open:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}
.agent-ops-message {
  margin: -4px 0 0;
  padding: 8px 10px;
  border: 1px solid #d4e2f4;
  border-radius: 8px;
  background: #f6f9fd;
  color: #315371;
  font-size: 13px;
}
.agent-grid {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 14px;
}
.agent-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 15px;
  border: 1px solid #d4e2f4;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 2px 10px rgba(15, 35, 70, 0.06);
}
.agent-card-head,
.agent-kicker {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}
.agent-type,
.agent-chip {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
  line-height: 1.3;
}
.agent-type {
  color: #0f3d7a;
  background: #eef5ff;
  border: 1px solid #d4e2f4;
}
.agent-chip {
  color: #2f5b3d;
  background: #eef8f1;
  border: 1px solid #cfe7d4;
}
.agent-card-title {
  margin: 0;
  font-size: 15px;
  color: #17324d;
}
.agent-card-desc {
  margin: 0;
  flex: 1;
  font-size: 13px;
  line-height: 1.5;
  color: #4a5b6d;
}
.agent-ops {
  display: grid;
  gap: 8px;
  padding-top: 4px;
  border-top: 1px solid #edf2f7;
}
.agent-ops-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.agent-ops-roles {
  align-items: flex-start;
  padding-left: 42px;
}
.agent-ops-label {
  min-width: 34px;
  color: #5a6b7b;
  font-size: 12px;
  line-height: 30px;
}
.agent-role-option {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-height: 30px;
  padding: 3px 7px;
  border: 1px solid #dce6f1;
  border-radius: 8px;
  background: #f9fbfe;
  color: #23384f;
  font-size: 12px;
  line-height: 1.25;
}
.agent-role-option input {
  margin: 0;
}
.agent-auth-summary {
  flex: 1;
  min-width: 130px;
  color: #8a96a3;
  font-size: 12px;
  line-height: 1.5;
}
.agent-card-foot {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}
.agent-open,
.agent-back {
  border: none;
  border-radius: 8px;
  background: #006be6;
  color: #fff;
  cursor: pointer;
  font-size: 13px;
}
.agent-open {
  padding: 6px 16px;
}
.agent-back {
  padding: 7px 12px;
  white-space: nowrap;
}
.agent-work-panel {
  margin-top: 12px;
  min-height: 420px;
  border: 1px solid #e2ebf6;
  border-radius: 8px;
  padding: 14px;
  background: #fff;
}
.agent-error {
  margin: 0;
  font-size: 13px;
  color: #b42318;
}
@media (max-width: 760px) {
  .agent-list-head,
  .agent-work-head {
    flex-direction: column;
  }
  .agent-tabs {
    width: 100%;
    overflow-x: auto;
  }
  .agent-list-actions {
    width: 100%;
    justify-content: flex-start;
  }
  .agent-ops-toolbar {
    width: 100%;
  }
  .agent-ops-roles {
    padding-left: 0;
  }
  .agent-back {
    align-self: flex-start;
  }
}
</style>
