import { ref } from 'vue';
import { authFetch } from './useAuth';
import { getProductRole } from './useProductRole';
import { newRequestId } from './useApiClient';
import { apiUrl } from './useApiBase';

export const PLATFORM_GUIDE_AGENT_ID = 'zw-platform-guide';

export interface GuideChatMessage {
  role: 'user' | 'assistant';
  text: string;
}

interface AgentRuntimeTaskResponse {
  session_id?: string;
  task_id?: string;
  status?: string;
  final_output?: unknown;
}

function formatFinalOutput(raw: unknown): string {
  if (raw == null) return '（无回复内容）';
  if (typeof raw === 'string') return raw.trim() || '（无回复内容）';
  if (typeof raw === 'object') {
    const obj = raw as Record<string, unknown>;
    for (const key of ['text', 'message', 'content', 'answer', 'final_output']) {
      const val = obj[key];
      if (typeof val === 'string' && val.trim()) return val.trim();
    }
    try {
      return JSON.stringify(raw, null, 2);
    } catch {
      return String(raw);
    }
  }
  return String(raw);
}

export function usePlatformGuideChat() {
  const messages = ref<GuideChatMessage[]>([]);
  const loading = ref(false);
  const error = ref<string | null>(null);
  const runtimeEnabled = ref<boolean | null>(null);

  async function probeRuntime(): Promise<boolean> {
    try {
      const resp = await authFetch(apiUrl('/health'));
      if (!resp.ok) {
        runtimeEnabled.value = false;
        return false;
      }
      const body = (await resp.json()) as { agent_runtime?: { enabled?: boolean } };
      const enabled = Boolean(body.agent_runtime?.enabled);
      runtimeEnabled.value = enabled;
      return enabled;
    } catch {
      runtimeEnabled.value = false;
      return false;
    }
  }

  async function ask(question: string): Promise<void> {
    const q = question.trim();
    if (!q || loading.value) return;

    messages.value.push({ role: 'user', text: q });
    loading.value = true;
    error.value = null;

    try {
      const enabled = runtimeEnabled.value ?? (await probeRuntime());
      if (!enabled) {
        throw new Error('AgentRuntime 未启用，问答不可用。请联系平台管理员开启。');
      }

      const resp = await authFetch(apiUrl('/api/agent-runtime/tasks'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({
          agent_id: PLATFORM_GUIDE_AGENT_ID,
          input: q,
          role: getProductRole().value,
          request_id: newRequestId('UI-GUIDE'),
        }),
      });

      if (resp.status === 503) {
        throw new Error('AgentRuntime 未启用或依赖未就绪（HTTP 503）');
      }
      if (!resp.ok) {
        const detail = await resp.text();
        throw new Error(`问答请求失败（HTTP ${resp.status}）${detail ? `：${detail.slice(0, 200)}` : ''}`);
      }

      const body = (await resp.json()) as AgentRuntimeTaskResponse;
      if (body.status === 'failed') {
        throw new Error('Agent 任务执行失败，请查看服务端日志');
      }
      messages.value.push({ role: 'assistant', text: formatFinalOutput(body.final_output) });
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      error.value = msg;
      messages.value.push({ role: 'assistant', text: `暂时无法回答：${msg}` });
    } finally {
      loading.value = false;
    }
  }

  function clear() {
    messages.value = [];
    error.value = null;
  }

  return {
    messages,
    loading,
    error,
    runtimeEnabled,
    probeRuntime,
    ask,
    clear,
  };
}
