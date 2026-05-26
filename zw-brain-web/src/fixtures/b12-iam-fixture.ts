/** B1.2 身份治理面板 fallback（后端不可达时展示结构样例，非验收依据）。 */

export interface PolicyCandidateItem {
  legacy_system: string;
  legacy_permission_ref: string;
  legacy_role_ref: string;
  capability_id: string;
  surface: string;
  candidate_status: string;
  evidence_json: Record<string, unknown>;
}

export interface PolicyCandidateListResult {
  tenant_id: string;
  summary: { total: number; status_counts: Record<string, number> };
  items: PolicyCandidateItem[];
}

export const POLICY_CANDIDATE_LIST_FIXTURE: PolicyCandidateListResult = {
  tenant_id: 'sd-default',
  summary: {
    total: 2,
    status_counts: { pending_review: 1, rejected: 1 },
  },
  items: [
    {
      legacy_system: 'dsp-bsp',
      legacy_permission_ref: 'FUNC_ZONE_PUBLISH',
      legacy_role_ref: 'ROLE_BUSIAUDIT',
      capability_id: 'zone.publish_topic_projection',
      surface: 'webui',
      candidate_status: 'pending_review',
      evidence_json: { source: 'fixture' },
    },
    {
      legacy_system: 'dsp-bsp',
      legacy_permission_ref: 'FUNC_LEGACY_ONLY',
      legacy_role_ref: 'ROLE_ORGAN_MANAGER',
      capability_id: 'request.list',
      surface: 'api',
      candidate_status: 'rejected',
      evidence_json: { source: 'fixture' },
    },
  ],
};
