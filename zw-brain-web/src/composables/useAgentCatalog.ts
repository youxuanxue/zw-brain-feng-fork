import { ref } from 'vue';
import { authFetch } from './useAuth';
import { apiUrl } from './useApiBase';
import { getProductRole } from './useProductRole';

// 拉取智能体目录。后端负责给出分类、岗位和可用性字段，前端只做展示与岗位过滤。
export interface AgentStateInfo {
  enabled?: boolean;
  allowed_roles?: string[];
  updated_by?: string | null;
  reason?: string | null;
  updated_at?: string | null;
}

export interface AgentInfo {
  id?: string;
  agent_id: string;
  name?: string;
  version?: string;
  trust_level?: string;
  description?: string;
  capability_skills?: string[];
  quick_questions?: string[];
  category?: string;
  surface?: string;
  agent_class?: 'A' | 'B' | string;
  agent_type_label?: string;
  runtime_ready?: boolean;
  enabled?: boolean;
  callable?: boolean;
  net_new?: string;
  tool_count?: number;
  assignable_roles?: string[];
  assignable_role_names?: string[];
  policy_allowed_roles?: string[];
  policy_allowed_role_names?: string[];
  // 调用方角色须 ∈ allowed_roles 才可用本应用（后端与 task 启动鉴权同口径）。
  // 画廊据此过滤卡片（无权不渲染，no-permission=invisible）；allowed_role_names 供 403 文案。
  allowed_roles?: string[];
  allowed_role_names?: string[];
  state?: AgentStateInfo;
}

export function useAgentCatalog() {
  const agents = ref<AgentInfo[]>([]);
  const loading = ref(false);
  const error = ref<string | null>(null);

  async function load(): Promise<void> {
    loading.value = true;
    error.value = null;
    try {
      const role = getProductRole().value;
      const resp = await authFetch(apiUrl(`/api/agent-runtime/agents?role=${encodeURIComponent(role)}`));
      if (!resp.ok) throw new Error('智能体列表暂时加载失败，请稍后重试。');
      const body = (await resp.json()) as { agents?: AgentInfo[] };
      agents.value = Array.isArray(body.agents)
        ? body.agents.map((agent) => ({ ...agent, agent_id: agent.agent_id || agent.id || '' })).filter((agent) => agent.agent_id)
        : [];
    } catch (e) {
      error.value = e instanceof Error ? e.message : '智能体列表暂时加载失败，请稍后重试。';
      agents.value = [];
    } finally {
      loading.value = false;
    }
  }

  async function updateAgentState(
    agentId: string,
    payload: { enabled: boolean; allowed_roles: string[]; reason?: string },
  ): Promise<AgentInfo> {
    const resp = await authFetch(apiUrl(`/api/agent-runtime/agents/${encodeURIComponent(agentId)}/state`), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ role: getProductRole().value, ...payload }),
    });
    if (!resp.ok) throw new Error('智能体状态更新失败，请稍后重试。');
    const body = (await resp.json()) as { agent?: AgentInfo };
    if (!body.agent) throw new Error('智能体状态更新失败，请稍后重试。');
    return body.agent;
  }

  async function reloadAgentRuntime(): Promise<Record<string, unknown>> {
    const resp = await authFetch(apiUrl('/api/agent-runtime/reload'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ role: getProductRole().value }),
    });
    if (!resp.ok) throw new Error('智能体重载失败，请检查智能体服务管理权限。');
    const body = (await resp.json()) as Record<string, unknown>;
    if (body.ok === false) {
      throw new Error(String(body.detail || '智能体重载未完成，请稍后重试。'));
    }
    return body;
  }

  return { agents, loading, error, load, updateAgentState, reloadAgentRuntime };
}
