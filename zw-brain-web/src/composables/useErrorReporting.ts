// 全局错误上报：Vue errorHandler + window error / unhandledrejection →
// POST /api/client-logs（后端落排障日志 rest.log，绝不写业务库）。
// postSkill 失败时 Error 上挂的 requestId 随上报体回传，后端用它 bind 日志
// 上下文 —— 前端报错与服务端同 id 的 access/capability 行可直接 grep 串联。
//
// 自我防护（reporter 自身绝不能成为新的错误源）：
//   - 去抖：同 kind+message+stack 前缀 30s 窗口只报 1 次
//   - 限流：全局 ≤10 条/分钟，超限丢弃
//   - 传输：纯 fetch + keepalive，不走 authFetch（无需会话/CSRF，避免 auth
//     bootstrap 阶段的递归依赖）；上报自身的一切异常一律吞
import type { App } from 'vue';
import { apiUrl } from './useApiBase';

const DEDUP_WINDOW_MS = 30_000;
const MAX_PER_MINUTE = 10;

const recentKeys = new Map<string, number>();
const sentTimestamps: number[] = [];

interface ClientErrorReport {
  kind: 'error' | 'unhandledrejection' | 'vue';
  message: string;
  stack?: string;
  component?: string;
  request_id?: string;
}

function shouldSend(key: string): boolean {
  const now = Date.now();
  const seenAt = recentKeys.get(key);
  if (seenAt !== undefined && now - seenAt < DEDUP_WINDOW_MS) return false;
  while (sentTimestamps.length && now - sentTimestamps[0] > 60_000) sentTimestamps.shift();
  if (sentTimestamps.length >= MAX_PER_MINUTE) return false;
  recentKeys.set(key, now);
  sentTimestamps.push(now);
  if (recentKeys.size > 100) {
    const cutoff = now - DEDUP_WINDOW_MS;
    for (const [k, t] of recentKeys) if (t < cutoff) recentKeys.delete(k);
  }
  return true;
}

function report(entry: ClientErrorReport): void {
  try {
    const key = `${entry.kind}:${entry.message}:${(entry.stack ?? '').slice(0, 200)}`;
    if (!shouldSend(key)) return;
    void fetch(apiUrl('/api/client-logs'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ...entry,
        url: window.location.href,
        occurred_at: new Date().toISOString(),
      }),
      keepalive: true,
    }).catch(() => undefined);
  } catch {
    /* 上报失败静默 —— 绝不递归 */
  }
}

function describeError(err: unknown): { message: string; stack?: string; request_id?: string } {
  if (err instanceof Error) {
    const requestId = (err as Error & { requestId?: string }).requestId;
    return { message: err.message, stack: err.stack, request_id: requestId };
  }
  return { message: String(err) };
}

export function installGlobalErrorReporting(app: App): void {
  app.config.errorHandler = (err, _instance, info) => {
    report({ kind: 'vue', component: info, ...describeError(err) });
    // 不吞掉默认行为：开发态控制台仍可见原始错误
    console.error(err);
  };
  window.addEventListener('error', (event) => {
    report({ kind: 'error', ...describeError(event.error ?? event.message) });
  });
  window.addEventListener('unhandledrejection', (event) => {
    report({ kind: 'unhandledrejection', ...describeError(event.reason) });
  });
}
