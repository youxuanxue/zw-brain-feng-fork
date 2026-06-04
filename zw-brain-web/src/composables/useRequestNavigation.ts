/** 从 request.create 响应或 invalid_state 错误里提取 request_id，供 P2 跳转。 */
export function resolveRequestIdFromAction(result: {
  ok: boolean;
  data?: unknown;
}): string | null {
  const data = result.data;
  if (data && typeof data === 'object') {
    const rec = data as Record<string, unknown>;
    // 缺陷 1 修复：request.create 是写能力，REST 把 handler 返回包成
    // `{ ok, skill_id, audit_id, result: { request_id, ... } }`。此前只看顶层
    // id/request_id（恒缺）→ resolveRequestId 恒返 null → 起草后不跳转、用户被扔在原地。
    // 先下钻到 result 信封再取 id（顶层无则回退 result，兼容读路径的裸返回）。
    const inner =
      rec.result && typeof rec.result === 'object' ? (rec.result as Record<string, unknown>) : rec;
    const direct = inner.id ?? inner.request_id ?? rec.id ?? rec.request_id;
    if (direct) return String(direct);
    const detail = String(rec.detail ?? '');
    const match = detail.match(/REQ-\d{4}-\d{2}-\d{2}-\d{4}/);
    if (match) return match[0];
  }
  return null;
}

export function navigateToRequestDetail(requestId: string): void {
  window.location.hash = `#/request-flow/request/${requestId}`;
}
