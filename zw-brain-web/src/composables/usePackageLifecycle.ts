import { ref, type Ref } from 'vue';
import { authFetch } from './useAuth';
import { newRequestId, postSkill } from './useApiClient';
import {
  EXPOSURE_MATRIX_FIXTURE,
  PACKAGE_LIST_FIXTURE,
  type ExposureMatrixResult,
  type PackageListResult,
} from '@/fixtures/b12-fixture';
import { normalizePackageRow } from '@/lib/packageDisplay';

// B1.2 接入扩展中心后端调用封装：
// - package.list（既有 capability_admin handler）
// - package.exposure.matrix.query（F4 新增 capability，含 209 manifest × 5 消费面矩阵）
// - package.review_decide / tenant.capability.enable / tenant.capability.disable /
//   package.rollback / package.trust_level.update（写敏感，human_confirmation_required=true）
//
// 与 F3-UI useAuditPanels 同 pattern：authFetch POST /api/skills/<slug> + fallback
// fixture；每个调用 UI 端生成 UI-PKG-* 前缀 request_id 让后端元审计 correlate。
// 共享 BFF 客户端见 useApiClient.ts。

export type PanelSource = 'idle' | 'loading' | 'live' | 'fixture';

// ---- 能力包列表 ----

export interface UsePackageListResult {
  data: Ref<PackageListResult | null>;
  source: Ref<PanelSource>;
  error: Ref<string | null>;
  load: (role?: string) => Promise<void>;
}

export function usePackageList(): UsePackageListResult {
  const data = ref<PackageListResult | null>(null);
  const source = ref<PanelSource>('idle');
  const error = ref<string | null>(null);

  async function load(role = 'ROLE_BUSIAUDIT'): Promise<void> {
    source.value = 'loading';
    error.value = null;
    try {
      const payload = await postSkill<PackageListResult>('package.list', {
        role,
        tenant_id: 'sd-default',
        request_id: newRequestId('UI-PKG-LIST'),
      });
      if (!payload || !Array.isArray(payload.items)) throw new Error('payload shape unexpected');
      data.value = {
        items: (payload.items as unknown[]).map((row) =>
          normalizePackageRow(row as Record<string, unknown>)
        ),
      };
      source.value = 'live';
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
      data.value = PACKAGE_LIST_FIXTURE;
      source.value = 'fixture';
    }
  }
  return { data, source, error, load };
}

// ---- 暴露矩阵 ----

export interface UseExposureMatrixResult {
  data: Ref<ExposureMatrixResult | null>;
  source: Ref<PanelSource>;
  error: Ref<string | null>;
  load: (
    filter: { journey?: string; status?: string; execution_binding?: string; surface?: string },
    role?: string
  ) => Promise<void>;
}

export function useExposureMatrix(): UseExposureMatrixResult {
  const data = ref<ExposureMatrixResult | null>(null);
  const source = ref<PanelSource>('idle');
  const error = ref<string | null>(null);

  async function load(
    filter: { journey?: string; status?: string; execution_binding?: string; surface?: string } = {},
    role = 'ROLE_BUSIAUDIT'
  ): Promise<void> {
    source.value = 'loading';
    error.value = null;
    try {
      const payload = await postSkill<ExposureMatrixResult>('package.exposure.matrix.query', {
        role,
        tenant_id: 'sd-default',
        request_id: newRequestId('UI-PKG-MAT'),
        ...filter,
      });
      if (!payload || !Array.isArray(payload.matrix)) throw new Error('payload shape unexpected');
      data.value = payload;
      source.value = 'live';
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
      data.value = EXPOSURE_MATRIX_FIXTURE;
      source.value = 'fixture';
    }
  }
  return { data, source, error, load };
}

// ---- 写操作（review / enable / disable / rollback / trust_level）----
//
// 全部走 invokeMutate 通用入口。`confirmed` 是必填参数（无默认值），调用方必须
// 在 UI 完成 window.confirm()/modal 后传 true——避免 composable 层固定 confirmed=true
// 绕过 backend manifest human_confirmation_required=true 硬门禁（xj-review R-002）。

export interface MutateResult {
  ok: boolean;
  audit_id?: string;
  result?: Record<string, unknown>;
  error?: string;
}

async function invokeMutate(
  skill: string,
  payload: Record<string, unknown>,
  role: string,
  confirmed: boolean
): Promise<MutateResult> {
  if (!confirmed) {
    return { ok: false, error: `${skill}: caller did not pass confirmed=true; backend gate would reject` };
  }
  try {
    const resp = await authFetch(`/api/skills/${skill}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({
        role,
        confirmed: true,
        tenant_id: 'sd-default',
        request_id: newRequestId(`UI-PKG-${skill.split('.').slice(-1)[0].toUpperCase()}`),
        ...payload,
      }),
    });
    if (resp.ok) {
      const data = (await resp.json()) as { ok?: boolean; audit_id?: string; result?: Record<string, unknown> };
      return { ok: true, audit_id: data.audit_id, result: data.result };
    }
    const detail = await resp.text().catch(() => '');
    return { ok: false, error: `HTTP ${resp.status}: ${detail || skill}` };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) };
  }
}

export async function reviewPackage(
  packageId: string,
  decision: 'approve' | 'return_for_fix' | 'reject',
  confirmed: boolean,
  role = 'ROLE_BUSIAUDIT'
): Promise<MutateResult> {
  return invokeMutate('package.review_decide', { package_id: packageId, decision }, role, confirmed);
}

export async function enableTenantCapability(
  packageId: string,
  confirmed: boolean,
  role = 'ROLE_BUSIAUDIT'
): Promise<MutateResult> {
  return invokeMutate('tenant.capability.enable', { package_id: packageId }, role, confirmed);
}

export async function disableTenantCapability(
  packageId: string,
  confirmed: boolean,
  role = 'ROLE_BUSIAUDIT'
): Promise<MutateResult> {
  return invokeMutate('tenant.capability.disable', { package_id: packageId }, role, confirmed);
}

export async function rollbackPackage(
  packageId: string,
  reason: string,
  confirmed: boolean,
  role = 'ROLE_BUSIAUDIT'
): Promise<MutateResult> {
  return invokeMutate('package.rollback', { package_id: packageId, reason }, role, confirmed);
}

export async function updatePackageTrustLevel(
  packageId: string,
  newLevel: 'baseline' | 'reviewed' | 'restricted' | 'revoked',
  reason: string,
  confirmed: boolean,
  role = 'ROLE_BUSIAUDIT'
): Promise<MutateResult> {
  return invokeMutate(
    'package.trust_level.update',
    { package_id: packageId, trust_level: newLevel, reason },
    role,
    confirmed
  );
}
