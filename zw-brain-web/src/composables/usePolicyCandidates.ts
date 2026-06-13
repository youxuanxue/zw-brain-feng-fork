import { ref, type Ref } from 'vue';
import { authFetch } from './useAuth';
import { newRequestId, postSkill } from './useApiClient';
import { applyPanelFallback } from '@/lib/panelFallback';
import {
  POLICY_CANDIDATE_LIST_FIXTURE,
  type PolicyCandidateItem,
  type PolicyCandidateListResult,
} from '@/fixtures/b12-iam-fixture';

// 'error' = 生产构建下 API 失败的诚实不可用态（R-007）。
export type PanelSource = 'idle' | 'loading' | 'live' | 'fixture' | 'error';

export interface ReviewCandidatesResult {
  ok: boolean;
  audit_id?: string;
  result?: Record<string, unknown>;
  error?: string;
}

export interface UsePolicyCandidatesResult {
  data: Ref<PolicyCandidateListResult | null>;
  source: Ref<PanelSource>;
  error: Ref<string | null>;
  load: (opts?: { role?: string; candidateStatus?: string }) => Promise<void>;
  review: (
    items: PolicyCandidateItem[],
    decision: 'approve' | 'reject' | 'approve_and_apply',
    role: string,
    reviewNote?: string
  ) => Promise<ReviewCandidatesResult>;
}

function buildListQuery(role: string, candidateStatus?: string): string {
  const params = new URLSearchParams({ role, tenant_id: 'sd-default' });
  if (candidateStatus) params.set('candidate_status', candidateStatus);
  return `/api/skills/governance.policy_candidate.list?${params.toString()}`;
}

export function usePolicyCandidates(): UsePolicyCandidatesResult {
  const data = ref<PolicyCandidateListResult | null>(null);
  const source = ref<PanelSource>('idle');
  const error = ref<string | null>(null);

  async function load(opts?: { role?: string; candidateStatus?: string }): Promise<void> {
    const role = opts?.role ?? 'ROLE_BUSIAUDIT';
    source.value = 'loading';
    error.value = null;
    try {
      const resp = await authFetch(buildListQuery(role, opts?.candidateStatus), {
        headers: { Accept: 'application/json' },
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const payload = (await resp.json()) as PolicyCandidateListResult;
      if (!payload || !Array.isArray(payload.items)) throw new Error('payload shape unexpected');
      data.value = payload;
      source.value = 'live';
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
      applyPanelFallback({ data, source }, POLICY_CANDIDATE_LIST_FIXTURE, null);
    }
  }

  async function review(
    items: PolicyCandidateItem[],
    decision: 'approve' | 'reject' | 'approve_and_apply',
    role: string,
    reviewNote = ''
  ): Promise<ReviewCandidatesResult> {
    if (!items.length) return { ok: false, error: '未选择候选记录' };
    try {
      const payload = await postSkill<{ ok?: boolean; audit_id?: string; result?: Record<string, unknown> }>(
        'governance.policy_candidate.review',
        {
          role,
          tenant_id: 'sd-default',
          decision,
          confirmed: true,
          review_note: reviewNote,
          request_id: newRequestId('UI-IAM-REVIEW'),
          items: items.map((it) => ({
            legacy_system: it.legacy_system,
            legacy_permission_ref: it.legacy_permission_ref,
            capability_id: it.capability_id,
          })),
        }
      );
      return { ok: Boolean(payload?.ok ?? true), audit_id: payload?.audit_id, result: payload?.result };
    } catch (e) {
      return { ok: false, error: e instanceof Error ? e.message : String(e) };
    }
  }

  return { data, source, error, load, review };
}
