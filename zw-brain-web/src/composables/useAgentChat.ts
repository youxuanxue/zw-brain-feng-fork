import { ref } from 'vue';
import { authFetch } from './useAuth';
import { getProductRole } from './useProductRole';
import { newRequestId } from './useApiClient';
import { apiUrl } from './useApiBase';

// 通用 Agent 对话引擎：「POST 提交任务 → 轮询到终端态」。任何内置 Agent（平台指南副驾、
// 找数副驾、智能体工作台…）共用本引擎，只需传 agentId。角色取当前产品角色（顶部岗位切换），
// 后端按该角色对 Agent 绑定的能力做权限门控（无权时任务侧返错，本引擎透传错误文案）。

/** 轮询间隔（毫秒） */
const POLL_INTERVAL_MS = 1_500;
/** 轮询超时（毫秒），超过此时间仍未结束则视为超时 */
const POLL_TIMEOUT_MS = 300_000;

/** 终端状态列表 — 到达其中之一即停止轮询 */
const TERMINAL_STATUSES = new Set(['completed', 'failed', 'cancelled', 'timeout']);

export interface AgentChatMessage {
  role: 'user' | 'assistant';
  text: string;
}

export interface UseAgentChatOptions {
  /** request_id 前缀，便于按来源排障（默认 UI-AGENT）。 */
  requestPrefix?: string;
  /** 控制台日志前缀（默认 AgentChat）。 */
  logPrefix?: string;
  /**
   * 本 Agent 可用的岗位中文名（来自 /agents 的 allowed_role_names，与后端 task 启动
   * 鉴权同口径）。用于 403 文案明确列出「可切换到」的具体岗位，而不是空泛的「有权岗位」。
   */
  allowedRoleNames?: string[];
}

interface AgentRuntimeTaskResponse {
  session_id?: string;
  task_id?: string;
  status?: string;
  final_output?: unknown;
}

function formatFinalOutput(raw: unknown): string {
  if (raw == null) return '（无回复内容）';
  if (typeof raw === 'string') return sanitizeAssistantText(raw.trim() || '（无回复内容）');
  if (typeof raw === 'object') {
    const obj = raw as Record<string, unknown>;
    for (const key of ['text', 'message', 'content', 'answer', 'final_output']) {
      const val = obj[key];
      if (typeof val === 'string' && val.trim()) return sanitizeAssistantText(val.trim());
    }
    try {
      return sanitizeAssistantText(JSON.stringify(raw, null, 2));
    } catch {
      return sanitizeAssistantText(String(raw));
    }
  }
  return sanitizeAssistantText(String(raw));
}

export function sanitizeAssistantText(text: string): string {
  return text
    .replace(/任务执行失败，请查看服务端日志/g, '本次智能分析没有形成可用答案，请换一个问题或稍后重试')
    .replace(/查看服务端日志/g, '联系平台运维员')
    .replace(/\bHTTP\s+\d{3}\b/gi, '服务暂不可用')
    .replace(/智能问答服务暂未就绪，请稍后重试。?/g, '当前助手暂不可用。')
    .replace(/智能问答服务暂不可用，请稍后重试。?/g, '当前助手暂不可用。')
    .replace(/\bAgentRuntime\s+unreachable\b/gi, '当前助手暂不可用')
    .replace(/\bagent[_-]?runtime[_-]?unreachable\b/gi, '当前助手暂不可用')
    .replace(/\bagent[_-]?runtime[_-]?disabled\b/gi, '当前助手暂不可用')
    .replace(/\bagent[_-]?runtime[_-]?not[_-]?found\b/gi, '当前助手暂不可用')
    .replace(/\bAgentRuntime\b/g, '智能助手')
    .replace(/\bAgent Runtime\b/g, '智能助手')
    .replace(/平台指南\s*Agent/g, '平台指南')
    .replace(/Agent\s*列表接口/g, '助手列表接口')
    .replace(/可用的\s*Agent/g, '可用助手')
    .replace(/等\s*Agent/g, '等助手');
}

function agentErrorMessage(status: number, detail = ''): string {
  if (status === 503) return '当前助手暂不可用。';
  if (status >= 500) return '当前助手暂不可用。';
  if (/agent[_-]?runtime|AgentRuntime|服务端日志|HTTP\s+\d{3}/i.test(detail)) {
    return '当前助手暂不可用。';
  }
  return '智能问答暂时无法处理这个问题，请换一种问法或稍后重试。';
}

export function useAgentChat(agentId: string, options?: UseAgentChatOptions) {
  const requestPrefix = options?.requestPrefix ?? 'UI-AGENT';
  const LOG_PREFIX = `[${options?.logPrefix ?? 'AgentChat'}]`;
  const logStep = (step: string, ...args: unknown[]) =>
    console.log(`%c${LOG_PREFIX} ${step}`, 'color:#4a9eff;font-weight:bold', ...args);
  const logWarn = (step: string, ...args: unknown[]) =>
    console.warn(`%c${LOG_PREFIX} ⚠️ ${step}`, 'color:#f5a623;font-weight:bold', ...args);
  const logError = (step: string, ...args: unknown[]) =>
    console.error(`%c${LOG_PREFIX} ❌ ${step}`, 'color:#e74c3c;font-weight:bold', ...args);
  const logOk = (step: string, ...args: unknown[]) =>
    console.log(`%c${LOG_PREFIX} ✅ ${step}`, 'color:#27ae60;font-weight:bold', ...args);

  const messages = ref<AgentChatMessage[]>([]);
  const loading = ref(false);
  const error = ref<string | null>(null);
  const runtimeEnabled = ref<boolean | null>(null);
  // 轮询取消：组件卸载（返回列表 / 切换应用 / 离开路由）后停掉后台轮询，
  // 否则 pollUntilTerminal 会对已销毁组件继续每 1.5s 打一次 GET 最多 5 分钟，
  // 反复 open/back 还会叠加多个游离轮询。调用方在 onUnmounted 里调用 stop()。
  let cancelled = false;
  function stop(): void {
    cancelled = true;
  }

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

  async function pollUntilTerminal(taskId: string, overallTimeout: number): Promise<AgentRuntimeTaskResponse> {
    const deadline = Date.now() + overallTimeout;
    let lastStatus = 'pending';
    let pollCount = 0;
    logStep(`开始轮询 task_id=${taskId}，总超时=${overallTimeout / 1000}s`);
    while (!cancelled && Date.now() < deadline) {
      pollCount++;
      const resp = await authFetch(apiUrl(`/api/agent-runtime/tasks/${taskId}`), { signal: null });
      if (!resp.ok) {
        if (resp.status === 404) {
          await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
          continue;
        }
        const detail = await resp.text().catch(() => '');
        logError(`[轮询 #${pollCount}] 失败 status=${resp.status}`, detail.slice(0, 200));
        throw new Error(agentErrorMessage(resp.status, detail));
      }
      const body = (await resp.json()) as AgentRuntimeTaskResponse;
      lastStatus = body.status || 'pending';
      if (TERMINAL_STATUSES.has(lastStatus)) {
        logOk(`到达终端状态 status=${lastStatus}（共 ${pollCount} 次轮询）`);
        return body;
      }
      await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
    }
    if (cancelled) {
      logWarn(`轮询取消：task_id=${taskId}（组件已卸载）`);
      return { status: 'cancelled' };
    }
    logWarn(`轮询超时：task_id=${taskId}，最后状态=${lastStatus}`);
    return { status: 'timeout', final_output: `轮询超时（${overallTimeout / 1000} 秒）` };
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
        throw new Error('当前助手暂不可用。');
      }
      logStep('[Step 1] POST /api/agent-runtime/tasks');
      const resp = await authFetch(apiUrl('/api/agent-runtime/tasks'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({
          agent_id: agentId,
          input: q,
          role: getProductRole().value,
          request_id: newRequestId(requestPrefix),
        }),
      });
      if (resp.status === 503) {
        throw new Error('当前助手暂不可用。');
      }
      if (resp.status === 403) {
        const names = options?.allowedRoleNames ?? [];
        const suffix = names.length ? `可切换到：${names.join(' / ')}。` : '';
        throw new Error(`当前岗位无权使用本应用所需的数据能力，请切换到有权岗位后重试。${suffix}`);
      }
      if (!resp.ok) {
        const detail = await resp.text();
        throw new Error(agentErrorMessage(resp.status, detail));
      }
      const body = (await resp.json()) as AgentRuntimeTaskResponse;

      const handleTerminal = (b: AgentRuntimeTaskResponse) => {
        if (b.status === 'failed') {
          const detail = formatFinalOutput(b.final_output);
          throw new Error(
            detail && detail !== '（无回复内容）'
              ? detail
              : '本次智能分析没有形成可用答案，请换一个问题或稍后重试。'
          );
        }
        if (b.status === 'cancelled') throw new Error('本次智能分析已停止，请重新发起。');
        if (b.status === 'timeout') throw new Error('本次智能分析耗时较长，请稍后重试。');
        messages.value.push({ role: 'assistant', text: formatFinalOutput(b.final_output) });
      };

      if (TERMINAL_STATUSES.has(body.status || '')) {
        handleTerminal(body);
        return;
      }
      const taskId = body.task_id;
      if (!taskId) {
        throw new Error('智能问答服务暂不可用，请稍后重试。');
      }
      const finalBody = await pollUntilTerminal(taskId, POLL_TIMEOUT_MS);
      if (cancelled) return; // 组件已卸载：不要把结果写进游离的 messages ref
      handleTerminal(finalBody);
    } catch (e) {
      const msg = sanitizeAssistantText(e instanceof Error ? e.message : String(e));
      logError(`ask() 失败: ${msg}`);
      error.value = msg;
      messages.value.push({ role: 'assistant', text: msg });
    } finally {
      loading.value = false;
    }
  }

  function clear() {
    messages.value = [];
    error.value = null;
  }

  return { messages, loading, error, runtimeEnabled, probeRuntime, ask, clear, stop };
}
