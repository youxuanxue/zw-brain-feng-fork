import { ref, type Ref } from 'vue';
import { authFetch } from './useAuth';
import { newRequestId, postSkill } from './useApiClient';
import { getProductRole } from './useProductRole';
import type { PackageListResult } from '@/lib/packageDisplay';
import { normalizePackageRow } from '@/lib/packageDisplay';
import { apiUrl } from './useApiBase';

// B1.2 外部系统后端调用封装：
// - package.list（既有 capability_admin handler）
// - package.review_decide / tenant.capability.enable / tenant.capability.disable /
//   package.rollback / package.trust_level.update（写敏感，human_confirmation_required=true）
//
// 角色一律取会话当前岗位（getProductRole），不再硬编码：D55/P2 外部系统收归平台
// 运维员后，固定 role payload 会让真实单岗位会话被 resolve_trusted_role 拒（403）。
// 加载失败不再回落 fixture 假数据——403/失败诚实呈现（D11），fixture 掩盖过整面权限错配。
// 每个调用 UI 端生成 UI-PKG-* 前缀 request_id 让后端元审计 correlate。

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

  async function load(role?: string): Promise<void> {
    source.value = 'loading';
    error.value = null;
    try {
      const payload = await postSkill<PackageListResult>('package.list', {
        role: role ?? getProductRole().value,
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
      // 诚实失败：不回落 fixture（假数据曾掩盖整面 403），页面按 error 呈现。
      error.value = e instanceof Error ? e.message : String(e);
      data.value = null;
      source.value = 'idle';
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
  role: string | undefined,
  confirmed: boolean
): Promise<MutateResult> {
  if (!confirmed) {
    return { ok: false, error: `${skill}: caller did not pass confirmed=true; backend gate would reject` };
  }
  try {
    const resp = await authFetch(apiUrl(`/api/skills/${skill}`), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({
        role: role ?? getProductRole().value,
        confirmed: true,
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
  role?: string
): Promise<MutateResult> {
  return invokeMutate('package.review_decide', { package_id: packageId, decision }, role, confirmed);
}

export async function enableTenantCapability(
  packageId: string,
  confirmed: boolean,
  role?: string
): Promise<MutateResult> {
  return invokeMutate('tenant.capability.enable', { package_id: packageId }, role, confirmed);
}

export async function disableTenantCapability(
  packageId: string,
  confirmed: boolean,
  role?: string
): Promise<MutateResult> {
  return invokeMutate('tenant.capability.disable', { package_id: packageId }, role, confirmed);
}

export async function rollbackPackage(
  packageId: string,
  reason: string,
  confirmed: boolean,
  role?: string
): Promise<MutateResult> {
  return invokeMutate('package.rollback', { package_id: packageId, reason }, role, confirmed);
}

export async function updatePackageTrustLevel(
  packageId: string,
  newLevel: 'baseline' | 'reviewed' | 'restricted' | 'revoked',
  reason: string,
  confirmed: boolean,
  role?: string
): Promise<MutateResult> {
  return invokeMutate(
    'package.trust_level.update',
    { package_id: packageId, trust_level: newLevel, reason },
    role,
    confirmed
  );
}
