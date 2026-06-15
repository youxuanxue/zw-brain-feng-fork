import { ref } from 'vue';
import { authFetch } from './useAuth';
import { getProductRole } from './useProductRole';
import { newRequestId } from './useApiClient';
import { apiUrl } from './useApiBase';

export const PLATFORM_GUIDE_AGENT_ID = 'zw-platform-guide';

/** 轮询间隔（毫秒） */
const POLL_INTERVAL_MS = 1_500;
/** 轮询超时（毫秒），超过此时间仍未结束则视为超时 */
const POLL_TIMEOUT_MS = 300_000;

/** 终端状态列表 — 到达其中之一即停止轮询 */
const TERMINAL_STATUSES = new Set(['completed', 'failed', 'cancelled', 'timeout']);

// ========================================================================
// 日志工具 — 每个关键步骤输出带时间戳的日志，标记为 [PlatformGuide]
// ========================================================================
const LOG_PREFIX = '[PlatformGuide]';
function logStep(step: string, ...args: unknown[]) {
  console.log(`%c${LOG_PREFIX} ${step}`, 'color:#4a9eff;font-weight:bold', ...args);
}
function logWarn(step: string, ...args: unknown[]) {
  console.warn(`%c${LOG_PREFIX} ⚠️ ${step}`, 'color:#f5a623;font-weight:bold', ...args);
}
function logError(step: string, ...args: unknown[]) {
  console.error(`%c${LOG_PREFIX} ❌ ${step}`, 'color:#e74c3c;font-weight:bold', ...args);
}
function logOk(step: string, ...args: unknown[]) {
  console.log(`%c${LOG_PREFIX} ✅ ${step}`, 'color:#27ae60;font-weight:bold', ...args);
}

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

/**
 * 轮询等待任务结束，最多等待 POLL_TIMEOUT_MS。
 * 返回终端状态下的 task response（含 final_output）。
 */
async function pollUntilTerminal(taskId: string, overallTimeout: number): Promise<AgentRuntimeTaskResponse> {
  const deadline = Date.now() + overallTimeout;
  let lastStatus = 'pending';
  let pollCount = 0;

  logStep(`开始轮询 task_id=${taskId}，总超时=${overallTimeout / 1000}s，轮询间隔=${POLL_INTERVAL_MS}ms`);

  while (Date.now() < deadline) {
    pollCount++;
    logStep(`[轮询 #${pollCount}] GET /api/agent-runtime/tasks/${taskId}（lastStatus=${lastStatus}，已用时间=${((Date.now() - (deadline - overallTimeout)) / 1000).toFixed(1)}s）`);

    // 跳过 AbortSignal 超时（authFetch 内部有 15s 默认超时，轮询时跳过）
    const resp = await authFetch(apiUrl(`/api/agent-runtime/tasks/${taskId}`), {
      signal: null, // 跳过浏览器超时，由 caller 的 deadline 控制
    });
    if (!resp.ok) {
      // 404 可能是任务尚未就绪，短暂等待后重试
      if (resp.status === 404) {
        logWarn(`[轮询 #${pollCount}] GET 返回 404（任务尚未就绪），${POLL_INTERVAL_MS}ms 后重试`);
        await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
        continue;
      }
      const detail = await resp.text().catch(() => '');
      const errMsg = `轮询任务失败（HTTP ${resp.status}）${detail ? `：${detail.slice(0, 200)}` : ''}`;
      logError(`[轮询 #${pollCount}] ${errMsg}`);
      throw new Error(errMsg);
    }

    const body = (await resp.json()) as AgentRuntimeTaskResponse;
    lastStatus = body.status || 'pending';

    logStep(`[轮询 #${pollCount}] 服务端返回 status=${lastStatus}${body.final_output ? `，有 final_output` : ''}`);

    if (TERMINAL_STATUSES.has(lastStatus)) {
      logOk(`[轮询 #${pollCount}] 到达终端状态 status=${lastStatus}，停止轮询（共 ${pollCount} 次）`);
      return body;
    }

    logStep(`[轮询 #${pollCount}] 非终端状态，${POLL_INTERVAL_MS}ms 后继续轮询`);
    // 非终端状态 → 等一会再轮询
    await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
  }

  // 超时
  logWarn(`轮询超时：task_id=${taskId}，共轮询 ${pollCount} 次，耗时 ${overallTimeout / 1000}s，最后状态=${lastStatus}`);
  return { status: 'timeout', final_output: `轮询超时（${overallTimeout / 1000} 秒）` };
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

    logStep(`ask() 开始，问题="${q.slice(0, 60)}..."`);

    try {
      const enabled = runtimeEnabled.value ?? (await probeRuntime());
      if (!enabled) {
        logWarn('AgentRuntime 未启用');
        throw new Error('AgentRuntime 未启用，问答不可用。请联系平台管理员开启。');
      }
      logOk('AgentRuntime 已启用');

      // ---- Step 1: 提交任务 ----
      logStep('[Step 1] POST /api/agent-runtime/tasks — 提交任务');
      const postStartTime = Date.now();
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
      const postElapsed = Date.now() - postStartTime;
      logStep(`[Step 1] POST 响应耗时=${postElapsed}ms，HTTP ${resp.status}`);

      if (resp.status === 503) {
        logWarn('POST 返回 503 — AgentRuntime 未启用');
        throw new Error('AgentRuntime 未启用或依赖未就绪（HTTP 503）');
      }
      if (!resp.ok) {
        const detail = await resp.text();
        const errMsg = `问答请求失败（HTTP ${resp.status}）${detail ? `：${detail.slice(0, 200)}` : ''}`;
        logError(`[Step 1] ${errMsg}`);
        throw new Error(errMsg);
      }

      const body = (await resp.json()) as AgentRuntimeTaskResponse;
      logStep(`[Step 1] POST 返回 body: ${JSON.stringify({ ...body, final_output: body.final_output ? '(有内容)' : undefined })}`);

      // ---- Step 2: 如果服务端直接返回了终端结果，直接处理 ----
      if (TERMINAL_STATUSES.has(body.status || '')) {
        logStep(`[Step 2] POST 直接返回终端状态 status=${body.status}`);
        if (body.status === 'failed') {
          throw new Error('Agent 任务执行失败，请查看服务端日志');
        }
        if (body.status === 'cancelled') {
          throw new Error('Agent 任务被取消');
        }
        if (body.status === 'timeout') {
          throw new Error('Agent 任务响应超时');
        }
        // completed
        logOk('[Step 2] 直接拿到最终结果');
        messages.value.push({ role: 'assistant', text: formatFinalOutput(body.final_output) });
        return;
      }

      // ---- Step 3: status === 'pending' → 轮询 ----
      const taskId = body.task_id;
      if (!taskId) {
        logError('[Step 3] POST 未返回 task_id');
        throw new Error('服务端未返回 task_id，无法轮询');
      }
      logStep(`[Step 3] POST 返回 pending，启动轮询 task_id=${taskId}，总超时=${POLL_TIMEOUT_MS / 1000}s`);

      const finalBody = await pollUntilTerminal(taskId, POLL_TIMEOUT_MS);

      logStep(`[Step 3] 轮询结束，status=${finalBody.status}`);

      if (finalBody.status === 'failed') {
        throw new Error('Agent 任务执行失败，请查看服务端日志');
      }
      if (finalBody.status === 'cancelled') {
        throw new Error('Agent 任务被取消');
      }
      if (finalBody.status === 'timeout') {
        throw new Error('Agent 任务响应超时');
      }
      // completed
      logOk('[Step 3] 成功获取最终结果');
      messages.value.push({ role: 'assistant', text: formatFinalOutput(finalBody.final_output) });
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      logError(`ask() 失败: ${msg}`);
      error.value = msg;
      messages.value.push({ role: 'assistant', text: `暂时无法回答：${msg}` });
    } finally {
      loading.value = false;
      logStep('ask() 结束');
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
