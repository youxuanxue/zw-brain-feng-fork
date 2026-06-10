/** B1.2 能力包列表：对齐后端 snapshot 字段（camelCase）与 UI 契约（snake_case）。 */

export interface PackageRow {
  id: string;
  name: string;
  slug: string;
  status: string; // pending / approved / active / rolled-back / suspended / rejected / revoked
  version: string;
  rollback_target: string;
  trust_level: string; // baseline / reviewed / restricted / revoked （B1.2 业务字段）
  source: string;
  desc: string;
}

export interface PackageListResult {
  items: PackageRow[];
}

const TRUST_LEVELS = ['baseline', 'reviewed', 'restricted', 'revoked'] as const;
export type PackageTrustLevel = (typeof TRUST_LEVELS)[number];

export function normalizeTrustLevel(raw: unknown): PackageTrustLevel {
  const v = String(raw ?? 'baseline').trim();
  return (TRUST_LEVELS as readonly string[]).includes(v) ? (v as PackageTrustLevel) : 'baseline';
}

/** 将 package.list 单条原始项投影为 UI 行。 */
export function normalizePackageRow(raw: Record<string, unknown>): PackageRow {
  const slug = String(raw.slug ?? '');
  return {
    id: String(raw.id ?? ''),
    // 名字绝不退化成整段描述：有 name 用 name，否则退到技术编号（slug），描述单列在 desc 字段。
    name: String(raw.name ?? slug),
    slug,
    status: String(raw.status ?? ''),
    version: String(raw.version ?? raw.registeredVersion ?? '—'),
    rollback_target: String(raw.rollback_target ?? raw.rollbackTarget ?? ''),
    trust_level: normalizeTrustLevel(raw.trust_level ?? raw.trustLevel),
    source: String(raw.source ?? ''),
    desc: String(raw.desc ?? ''),
  };
}

export function trustPillClass(level: string): string {
  switch (normalizeTrustLevel(level)) {
    case 'reviewed':
      return 'trust-reviewed';
    case 'restricted':
      return 'trust-restricted';
    case 'revoked':
      return 'trust-revoked';
    default:
      return 'trust-baseline';
  }
}
