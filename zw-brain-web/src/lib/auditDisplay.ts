/** B1 合规/接入页：审计与数据源字段的用户可见文案（R12，禁止英文枚举直出）。 */

export function formatDataSource(src: string): string {
  const map: Record<string, string> = {
    live: '实时数据',
    fixture: '演示数据',
    loading: '加载中',
    idle: '',
    error: '不可用',
  };
  return map[src] ?? '';
}

export function formatSeverity(severity: string): string {
  const map: Record<string, string> = {
    high: '高',
    medium: '中',
    low: '低',
  };
  return map[severity] ?? severity;
}

export function formatDeniedChainCount(total: number): string {
  if (total <= 0) return '该对象近期无拒绝访问记录。';
  return `共 ${total} 条拒绝访问链路。`;
}

export function formatActorLabel(actor: string): string {
  const raw = String(actor ?? '').trim();
  if (!raw) return '—';
  const parts = raw.split(':');
  const name = parts[parts.length - 1];
  if (name && /[\u4e00-\u9fff]/.test(name)) return name;
  return raw;
}

// ---------------------------------------------------------------------------
// \u5ba1\u8ba1\u679a\u4e3e \u2192 \u4e2d\u6587 label\uff08R12\uff1astatus-pill \u7c7b\u679a\u4e3e/\u6807\u8bc6\u7b26\u7981\u88f8 snake_case \u76f4\u51fa\uff09
//
// \u679a\u4e3e\u5168\u96c6\u6765\u6e90\uff08\u4e0a\u5e1d\u89c6\u89d2\u6838\u5bf9\uff0c2026-06-20\uff09\uff1a
//   \u00b7 audit_class\uff1azw_brain/shared/audit/store.py:59 CANONICAL_AUDIT_CLASSES\uff083 \u503c\uff0c
//     \u540e\u7aef normalize_audit_class \u5df2\u6536\u655b\uff1b\u6b64\u5904\u989d\u5916\u8986\u76d6 _AUDIT_CLASS_MAP \u5386\u53f2\u522b\u540d\u505a\u9632\u5fa1\uff09\u3002
//   \u00b7 dimension\uff1azw_brain/command/handlers/b1/audit.py:311 _dimension_value\uff084 \u503c\uff09\u3002
//   \u00b7 phase\uff1atests/integration/test_audit_replay.py\uff08before/validate/commit/anchor_enqueued/
//     after/error \u5168\u96c6\uff1b\u7ba1\u7ebf zw_brain/command/pipeline.py\uff09\u3002
//   \u00b7 event_type\uff1asemi-open\uff08capability_call \u9ed8\u8ba4 + \u5404 handler \u6d3e\u751f dotted \u503c\uff09\uff1b
//     \u5df2\u77e5\u5178\u578b\u503c\u7ed9 label\uff0c\u672a\u77e5 dotted/snake \u503c\u7531\u8c03\u7528\u4fa7\u964d\u7ea7\u8d70 title\uff08\u4e0d\u88f8\u51fa pill\uff09\u3002
//   \u00b7 rule\uff1azw_brain/command/handlers/b1/audit.py:387-475\uff083 \u6761\u786c\u7f16\u7801\u63a2\u6d4b\u89c4\u5219\uff09\u3002
//
// \u5171\u540c\u7eaa\u5f8b\uff1a\u672a\u77e5\u503c\u515c\u5e95\u8fd4\u56de\u539f\u503c\uff08\u4e0d\u541e\u6570\u636e\uff09\uff1b\u8c03\u7528\u4fa7\u5bf9\u4ecd\u662f\u5de5\u7a0b\u6001\u7684\u515c\u5e95\u503c
// \uff08\u5982\u70b9\u5206 skill_id / \u672a\u767b\u8bb0 event_type\uff09\u6539\u8d70 title \u5c5e\u6027\u9690\u85cf\uff0c\u4e0d\u76f4\u51fa\u4e3a\u53ef\u89c1\u6587\u6848\u3002
// ---------------------------------------------------------------------------

const AUDIT_CLASS_LABELS: Record<string, string> = {
  // 仅 3 个 canonical——后端 normalize_audit_class 在两条写路径(AuditStore.append/audit_bus.emit)
  // 强制收敛后才落库，别名永不以原形回读；意外值由 `?? raw` 兜底 + r12 渲染层守卫拦截。
  'write-critical': '\u5173\u952e\u5199\u64cd\u4f5c',
  'write-normal': '\u5e38\u89c4\u5199\u64cd\u4f5c',
  'read-sensitive': '\u654f\u611f\u8bfb\u64cd\u4f5c',
};

export function formatAuditClass(value: string): string {
  const raw = String(value ?? '').trim();
  if (!raw) return '\u2014';
  return AUDIT_CLASS_LABELS[raw] ?? raw;
}

const DIMENSION_LABELS: Record<string, string> = {
  audit_class: '\u64cd\u4f5c\u7c7b\u522b',
  actor: '\u64cd\u4f5c\u5bf9\u8c61',
  skill_id: '\u80fd\u529b',
  tenant_id: '\u79df\u6237',
};

export function formatDimension(value: string): string {
  const raw = String(value ?? '').trim();
  if (!raw) return '\u2014';
  return DIMENSION_LABELS[raw] ?? raw;
}

const PHASE_LABELS: Record<string, string> = {
  before: '\u6267\u884c\u524d',
  validate: '\u6821\u9a8c',
  commit: '\u63d0\u4ea4',
  anchor_enqueued: '\u5b58\u8bc1\u5165\u961f',
  after: '\u6267\u884c\u540e',
  error: '\u5931\u8d25',
};

export function formatPhase(value: string): string {
  const raw = String(value ?? '').trim();
  if (!raw) return '\u2014';
  return PHASE_LABELS[raw] ?? raw;
}

const RULE_LABELS: Record<string, string> = {
  'cross-tenant-read': '\u8de8\u79df\u6237\u8bfb\u53d6',
  'high-failure-rate': '\u9ad8\u9891\u5931\u8d25',
  'repeated-denied': '\u53cd\u590d\u62d2\u7edd',
};

export function formatRule(value: string): string {
  const raw = String(value ?? '').trim();
  if (!raw) return '\u2014';
  return RULE_LABELS[raw] ?? raw;
}

// \u80fd\u529b skill_id \u53cb\u597d\u540d\uff08\u672c\u8f6e\uff1a\u4ec5\u524d\u7aef\u8f7b\u91cf\u6620\u5c04\uff1b\u540e\u7aef capability \u5b57\u5178\u7559\u72ec\u7acb\u5de5\uff09\u3002
// \u70b9\u5206 skill_id\uff08\u5982 governance.policy_candidate.review\uff09\u4e00\u5f8b\u4e0d\u76f4\u51fa\u4e3a\u53ef\u89c1\u6587\u6848\u2014\u2014
// \u8c03\u7528\u4fa7\u628a\u539f id \u653e\u8fdb title \u5c5e\u6027\uff0c\u53ef\u89c1\u5904\u663e\u793a\u4e2d\u6587\u53cb\u597d\u540d\uff1b\u672a\u767b\u8bb0\u7684 id \u515c\u5e95\u56de
// \u300c\u80fd\u529b\u8c03\u7528\u300d\u8fd9\u4e00\u901a\u7528\u4e2d\u6587\uff08R12 \u4e0d\u88f8\u51fa\u70b9\u5206/snake token\uff09\uff0c\u539f id \u4ecd\u7559 title \u4e0d\u4e22\u3002
const CAPABILITY_NAME_LABELS: Record<string, string> = {
  'governance.policy_candidate.review': '\u4e13\u9898\u7b56\u7565\u5019\u9009\u5ba1\u6838',
  'application.resource.review': '\u8d44\u6e90\u7533\u8bf7\u5ba1\u6279',
  'application.grant.approve': '\u6388\u6743\u5ba1\u6279',
};

export function formatCapabilityName(skillId: string): string {
  const raw = String(skillId ?? '').trim();
  if (!raw) return '\u2014';
  // \u5df2\u767b\u8bb0 \u2192 \u4e2d\u6587\u53cb\u597d\u540d\uff1b\u672a\u767b\u8bb0 \u2192 \u901a\u7528\u4e2d\u6587\uff08\u7edd\u4e0d\u56de\u843d\u5230\u70b9\u5206/snake \u539f\u6587\uff0c\u539f id \u7531
  // \u8c03\u7528\u4fa7 title \u5c5e\u6027\u627f\u8f7d\uff0c\u53ef\u89c1\u6587\u6848\u6c38\u4e0d\u88f8\u51fa\u5de5\u7a0b\u6807\u8bc6\uff09\u3002
  return CAPABILITY_NAME_LABELS[raw] ?? '\u80fd\u529b\u8c03\u7528';
}
