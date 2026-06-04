// sd-default 真实切片回退；后端 /api/skills/package.* 不可达时使用。与 P1Workbench
// 同 pattern——真实部署一定走 API，不读这份 fixture。

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

export interface ExposureMatrixRow {
  skill_id: string;
  /** 人话名 / 说明（后端投影自 manifest title/description）；去 slug 上人话用。 */
  name?: string;
  description?: string;
  journey: string;
  status: string;
  execution_binding: string;
  audit_class: string;
  surfaces: string[];
  human_confirmation_required: boolean;
  trust_level: string;
}

export interface ExposureMatrixResult {
  matrix: ExposureMatrixRow[];
  totals: {
    manifests: number;
    by_surface: Record<string, number>;
    by_journey: Record<string, number>;
    by_status: Record<string, number>;
    by_execution_binding: Record<string, number>;
  };
  scanned: number;
}

export const PACKAGE_LIST_FIXTURE: PackageListResult = {
  items: [
    {
      id: 'PKG-DEMO-PETROMIND-001',
      name: '石化经营智能助手',
      slug: 'petromind',
      status: 'active',
      version: 'v1.4.2',
      rollback_target: 'v1.3.0',
      trust_level: 'reviewed',
      source: '外部接入',
      desc: 'PetroMind 利润经营智能体——读类只读 + 草稿生成；不写主状态。',
    },
    {
      id: 'PKG-DEMO-PETROINTEL-001',
      name: '外部情报采集器',
      slug: 'petrointel',
      status: 'pending',
      version: 'v0.9.1',
      rollback_target: '',
      trust_level: 'baseline',
      source: '外部接入',
      desc: 'PetroIntel 外部情报采集——待业务方审核确认。',
    },
    {
      id: 'PKG-DEMO-OPEN-WORLD-001',
      name: '数智世界 SPA',
      slug: 'open-world',
      status: 'rolled-back',
      version: 'v2.0.0',
      rollback_target: 'v2.1.0',
      trust_level: 'restricted',
      source: '外部接入',
      desc: '数智世界前端 SPA——回滚版本，定位 v2.1.0 性能回归。',
    },
  ],
};

export const EXPOSURE_MATRIX_FIXTURE: ExposureMatrixResult = {
  matrix: [
    {
      skill_id: 'audit.event.statistics',
      journey: 'b1',
      status: 'live',
      execution_binding: 'builtin',
      audit_class: 'read-sensitive',
      surfaces: ['webui', 'api', 'cli', 'mcp', 'a2a'],
      human_confirmation_required: false,
      trust_level: 'baseline',
    },
    {
      skill_id: 'package.rollback',
      journey: 'b1',
      status: 'live',
      execution_binding: 'builtin',
      audit_class: 'write-critical',
      surfaces: ['webui', 'api', 'cli', 'a2a'],
      human_confirmation_required: true,
      trust_level: 'baseline',
    },
    {
      skill_id: 'package.trust_level.update',
      journey: 'b1',
      status: 'live',
      execution_binding: 'builtin',
      audit_class: 'write-critical',
      surfaces: ['webui', 'api', 'cli', 'a2a'],
      human_confirmation_required: true,
      trust_level: 'baseline',
    },
    {
      skill_id: 'approval_flow.schema.commit',
      journey: 'j2',
      status: 'live',
      execution_binding: 'builtin',
      audit_class: 'write-critical',
      surfaces: ['webui', 'api', 'cli'],
      human_confirmation_required: true,
      trust_level: 'baseline',
    },
    {
      skill_id: 'form_schema.commit',
      journey: 'j2',
      status: 'live',
      execution_binding: 'builtin',
      audit_class: 'write-critical',
      surfaces: ['webui', 'api', 'cli'],
      human_confirmation_required: true,
      trust_level: 'baseline',
    },
  ],
  totals: {
    manifests: 209,
    by_surface: { webui: 178, api: 174, cli: 170, mcp: 60, a2a: 167 },
    by_journey: { j1: 59, j2: 42, b1: 50, infra: 17, external: 13, national: 14 },
    by_status: { live: 168, external: 13, 'deferred:wave-2': 28 },
    by_execution_binding: { builtin: 190, external_capability: 19 },
  },
  scanned: 5,
};
