// 与 sd-default canonical 同源切片；后端 /api/skills/audit.event.* 不可达
// （开发期未启 brain server 或鉴权失败）时兜底。真实部署一定走 API，不读这份 fixture。
//
// 数据范围：sd-default 单租户审计样本——3 phase 真实审批链 + 3 类异常事件 +
// 1 个 actor 的 denied 链 + statistics 4 桶聚合切片。与 P1Workbench 同 pattern
// （workbench-fixture.ts），仅当 BFF 链路断时回退。

export interface AuditEventRow {
  request_id: string;
  actor: string;
  skill_id: string;
  tenant_id: string;
  audit_class: string;
  event_type: string;
  phase: string;
  occurred_at: string;
}

export interface AuditQueryResult {
  items: AuditEventRow[];
  summary: {
    total: number;
    by_audit_class: Record<string, number>;
    by_skill: Record<string, number>;
    by_actor: Record<string, number>;
    first_occurred_at: string | null;
    last_occurred_at: string | null;
  };
}

export interface AuditReplayResult {
  request_id: string;
  items: (AuditEventRow & { payload: Record<string, unknown> })[];
  summary: AuditQueryResult['summary'];
}

export interface StatisticsBucket {
  bucket_key: string;
  by_dimension: Record<string, number>;
  total: number;
}

export interface AuditStatisticsResult {
  bucket: string;
  dimension: string;
  buckets: StatisticsBucket[];
  totals: Record<string, number>;
  scanned: number;
}

export interface AnomalyHit {
  rule: 'cross-tenant-read' | 'high-failure-rate' | 'repeated-denied';
  severity: 'low' | 'medium' | 'high';
  actor: string;
  skill_id?: string;
  tenant_id: string;
  evidence_request_ids: string[];
  occurrence_count: number;
  summary: string;
}

export interface AuditAnomalyResult {
  anomalies: AnomalyHit[];
  scanned: number;
}

export interface DeniedChainEntry {
  request_id: string;
  skill_id: string;
  denied_at: string;
  events: {
    phase: string;
    occurred_at: string;
    sanitized_payload: Record<string, unknown>;
  }[];
}

export interface AuditAccountabilityResult {
  actor: string;
  denied_chains: DeniedChainEntry[];
  total: number;
}

export interface InvestigationSummaryResult {
  summary: string;
  model: string;
  sanitized_input_digest: string;
  usage: Record<string, number>;
}

// 模拟一条 sd-default 真实审批链回放（来自 governance.policy_candidate.review）
export const REPLAY_FIXTURE: AuditReplayResult = {
  request_id: 'REQ-SD-GOV-001',
  items: [
    {
      request_id: 'REQ-SD-GOV-001',
      actor: 'user:gov:ROLE_BUSIAUDIT:平台运营员',
      skill_id: 'governance.policy_candidate.review',
      tenant_id: 'sd-default',
      audit_class: 'write-critical',
      event_type: 'package_lifecycle',
      phase: 'before',
      occurred_at: '2026-05-24T08:30:01Z',
      payload: { legacy_role_ref: 'ROLE_ORGAN_OPERATER', decision: 'pending' },
    },
    {
      request_id: 'REQ-SD-GOV-001',
      actor: 'user:gov:ROLE_BUSIAUDIT:平台运营员',
      skill_id: 'governance.policy_candidate.review',
      tenant_id: 'sd-default',
      audit_class: 'write-critical',
      event_type: 'package_lifecycle',
      phase: 'commit',
      occurred_at: '2026-05-24T08:30:03Z',
      payload: { legacy_role_ref: 'ROLE_ORGAN_OPERATER', decision: 'approve_and_apply' },
    },
    {
      request_id: 'REQ-SD-GOV-001',
      actor: 'user:gov:ROLE_BUSIAUDIT:平台运营员',
      skill_id: 'governance.policy_candidate.review',
      tenant_id: 'sd-default',
      audit_class: 'write-critical',
      event_type: 'package_lifecycle',
      phase: 'after',
      occurred_at: '2026-05-24T08:30:04Z',
      payload: { tenant_policy_persisted: true },
    },
  ],
  summary: {
    total: 3,
    by_audit_class: { 'write-critical': 3 },
    by_skill: { 'governance.policy_candidate.review': 3 },
    by_actor: { 'user:gov:ROLE_BUSIAUDIT:平台运营员': 3 },
    first_occurred_at: '2026-05-24T08:30:01Z',
    last_occurred_at: '2026-05-24T08:30:04Z',
  },
};

export const STATISTICS_FIXTURE: AuditStatisticsResult = {
  bucket: 'day',
  dimension: 'audit_class',
  buckets: [
    { bucket_key: '2026-05-22', by_dimension: { 'write-critical': 12, 'read-sensitive': 240 }, total: 252 },
    { bucket_key: '2026-05-23', by_dimension: { 'write-critical': 18, 'read-sensitive': 305 }, total: 323 },
    { bucket_key: '2026-05-24', by_dimension: { 'write-critical': 7, 'write-normal': 3, 'read-sensitive': 188 }, total: 198 },
  ],
  totals: { 'write-critical': 37, 'write-normal': 3, 'read-sensitive': 733 },
  scanned: 773,
};

export const ANOMALY_FIXTURE: AuditAnomalyResult = {
  anomalies: [
    {
      rule: 'high-failure-rate',
      severity: 'high',
      actor: 'user:gov:ROLE_ORGAN_OPERATER:王凯',
      skill_id: 'application.resource.review',
      tenant_id: 'sd-default',
      evidence_request_ids: ['REQ-2026-05-24-0114', 'REQ-2026-05-24-0118', 'REQ-2026-05-24-0121', 'REQ-2026-05-24-0125'],
      occurrence_count: 6,
      summary: '操作员王凯近 30 分钟内 6 次申请审批失败（阈值 3 次）',
    },
    {
      rule: 'repeated-denied',
      severity: 'high',
      actor: 'user:gov:ROLE_ORGAN_OPERATER:李兵',
      skill_id: 'application.grant.approve',
      tenant_id: 'sd-default',
      evidence_request_ids: ['REQ-2026-05-24-0098'],
      occurrence_count: 4,
      summary: '同一申请 REQ-2026-05-24-0098 连续 4 次 denied',
    },
    {
      rule: 'cross-tenant-read',
      severity: 'medium',
      actor: 'system:audit-sync',
      tenant_id: 'sd-default,backup-2026-05',
      evidence_request_ids: ['REQ-SYS-AUDIT-SYNC-001', 'REQ-SYS-AUDIT-SYNC-002'],
      occurrence_count: 32,
      summary: '同一调用方 system:audit-sync 在 2 个租户上有 read-sensitive 事件',
    },
  ],
  scanned: 773,
};

export const ACCOUNTABILITY_FIXTURE: AuditAccountabilityResult = {
  actor: 'user:gov:ROLE_ORGAN_OPERATER:王凯',
  total: 2,
  denied_chains: [
    {
      request_id: 'REQ-2026-05-24-0125',
      skill_id: 'application.resource.review',
      denied_at: '2026-05-24T09:14:33Z',
      events: [
        {
          phase: 'before',
          occurred_at: '2026-05-24T09:14:31Z',
          sanitized_payload: { resource_id: 'RES-PARK-2026-04', reason: 'rbac-check' },
        },
        {
          phase: 'error',
          occurred_at: '2026-05-24T09:14:33Z',
          sanitized_payload: { outcome: 'denied', reason: 'role_lacks_permission', actor_snapshot: 'sha1:abcd1234' },
        },
      ],
    },
    {
      request_id: 'REQ-2026-05-24-0121',
      skill_id: 'application.resource.review',
      denied_at: '2026-05-24T09:08:11Z',
      events: [
        {
          phase: 'before',
          occurred_at: '2026-05-24T09:08:10Z',
          sanitized_payload: { resource_id: 'RES-MED-2026-01' },
        },
        {
          phase: 'error',
          occurred_at: '2026-05-24T09:08:11Z',
          sanitized_payload: { outcome: 'denied', reason: 'tenant_policy_missing' },
        },
      ],
    },
  ],
};

export const SUMMARY_FIXTURE: InvestigationSummaryResult = {
  summary:
    '近 24 小时观察到 1 类 high-severity 高频失败（操作员王凯 6 次申请审批失败）+ 1 类 high-severity 重复 denied（同一申请 4 次）+ 1 类 medium 跨租户读痕迹。建议优先约谈高频失败操作员，复核重复 denied 涉及的策略匹配规则。',
  model: 'claude-sonnet-4-7-fixture',
  sanitized_input_digest: 'sha1:b11-fixture-stable',
  usage: { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 },
};
