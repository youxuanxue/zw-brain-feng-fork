// 共享 BFF 调用封装：3 个 B1 composable（useAuditPanels / usePackageLifecycle /
// useInvestigationSummary）原本各自 copy-paste 同款 postSkill + newRequestId
// 实现（xj-review #97 R-001）。抽到此处统一维护。
//
// 设计契约：
//   - postSkill<T>：薄包装 authFetch + JSON 头 + 错误抛出；不做 fallback（由
//     上层 composable 控制 fallback 策略）。
//   - newRequestId：生成 UI 端 request_id 让后端元审计 correlate；prefix 由
//     调用方提供（如 'UI-STAT' / 'UI-PKG-LIST' / 'UI-INV'），确保各 panel
//     可在审计回放里区分来源。
//
// 单租户 sd-default 与 confirmed 语义由调用方负责传入；本 client 不内置任
// 何业务字段，避免再一次「composable 层固定写 gate」失控（参见 R-002 设
// 计修正：confirmed 必须由调用栈显式传递）。

import { authFetch } from './useAuth';
import { apiUrl } from './useApiBase';

export async function postSkill<T>(skill: string, payload: Record<string, unknown>): Promise<T> {
  // X-Request-Id 让这次调用在服务端 rest.log 里可定位；失败时挂到 Error 上，
  // 全局错误上报（useErrorReporting）回传同一 id 完成前后端日志串联。
  const requestId = newRequestId('UI');
  const resp = await authFetch(apiUrl(`/api/skills/${skill}`), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      'X-Request-Id': requestId,
    },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    throw Object.assign(new Error(`HTTP ${resp.status} from ${skill}`), { requestId });
  }
  return (await resp.json()) as T;
}

export function newRequestId(prefix: string): string {
  const ts = new Date().toISOString().replace(/[-:.TZ]/g, '');
  const rand = Math.random().toString(36).slice(2, 8);
  return `${prefix}-${ts}-${rand}`;
}
