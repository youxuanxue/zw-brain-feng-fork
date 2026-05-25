/** 从 request.create 响应或 invalid_state 错误里提取 request_id，供 P2 跳转。 */
export function resolveRequestIdFromAction(result: {
  ok: boolean;
  data?: unknown;
}): string | null {
  const data = result.data;
  if (data && typeof data === 'object') {
    const rec = data as Record<string, unknown>;
    const direct = rec.id ?? rec.request_id;
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
