// Keep in sync with zw_brain/domain/application_dedupe.py (REQUEST_RECREATE + _STATUS_PRIORITY).
export const REQUEST_RECREATE_ALLOWED_STATUSES = new Set([
  'withdrawn',
  'revoked',
  'expired',
  'completed',
  'closed',
]);

const REQUEST_REOPEN_PRIORITY = new Map([
  ['draft', 100],
  ['need-fix', 95],
  ['supplementing', 92],
  ['summary-pending', 92],
  ['pending', 90],
  ['submitted', 90],
  ['under_review', 88],
  ['dept_approved', 85],
  ['approved', 80],
  ['granted', 75],
  ['effective', 75],
  ['change_pending', 60],
  ['suspended', 50],
  ['rejected', 40],
]);

function requestSortTime(request: Record<string, unknown>): string {
  return String(
    request.updatedAt ??
      request.updated_at ??
      request.submittedAt ??
      request.submitted_at ??
      request.createdAt ??
      request.created_at ??
      '',
  );
}

function preferExistingRequest(next: Record<string, unknown>, current: Record<string, unknown> | undefined): boolean {
  if (!current) return true;
  const nextScore = REQUEST_REOPEN_PRIORITY.get(String(next.status ?? '')) ?? 20;
  const currentScore = REQUEST_REOPEN_PRIORITY.get(String(current.status ?? '')) ?? 20;
  if (nextScore !== currentScore) return nextScore > currentScore;
  return requestSortTime(next) >= requestSortTime(current);
}

export function buildExistingRequestsByResource(
  requests: Array<Record<string, unknown>>,
): Map<string, Record<string, unknown>> {
  const mapped = new Map<string, Record<string, unknown>>();
  for (const request of requests) {
    if (request.mine !== true) continue;
    const resourceId = String(request.resourceId ?? request.resource_id ?? '');
    const requestId = String(request.id ?? '');
    const status = String(request.status ?? '');
    if (!resourceId || !requestId || REQUEST_RECREATE_ALLOWED_STATUSES.has(status)) continue;
    const current = mapped.get(resourceId);
    if (preferExistingRequest(request, current)) {
      mapped.set(resourceId, request);
    }
  }
  return mapped;
}
