import { ref } from 'vue';
import { authFetch } from './useAuth';
import { apiUrl } from './useApiBase';

// 拉取内置 Agent 目录（GET /api/agent-runtime/agents）。category 由后端从 AGENT.yaml
// labels.surface 派生（copilot / data-app），是 UI 落位（找数副驾 vs 数据应用）的单一事实源。
export interface AgentInfo {
  agent_id: string;
  name?: string;
  version?: string;
  trust_level?: string;
  description?: string;
  capability_skills?: string[];
  category?: string;
  // 调用方角色须 ∈ allowed_roles 才可用本应用（后端与 task 启动鉴权同口径）。
  // 画廊据此过滤卡片（无权不渲染，no-permission=invisible）；allowed_role_names 供 403 文案。
  allowed_roles?: string[];
  allowed_role_names?: string[];
}

export function useAgentCatalog() {
  const agents = ref<AgentInfo[]>([]);
  const loading = ref(false);
  const error = ref<string | null>(null);

  async function load(): Promise<void> {
    loading.value = true;
    error.value = null;
    try {
      const resp = await authFetch(apiUrl('/api/agent-runtime/agents'));
      if (!resp.ok) {
        throw new Error('暂时无法加载应用列表，请稍后重试。');
      }
      const body = (await resp.json()) as { agents?: AgentInfo[] };
      agents.value = Array.isArray(body.agents) ? body.agents : [];
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
      agents.value = [];
    } finally {
      loading.value = false;
    }
  }

  return { agents, loading, error, load };
}
