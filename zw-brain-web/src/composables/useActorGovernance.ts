import { ref, type Ref } from 'vue';
import { newRequestId, postSkill } from './useApiClient';
import { applyPanelFallback } from '@/lib/panelFallback';
import {
  ACCESS_MATRIX_FIXTURE,
  ACTOR_LIST_FIXTURE,
  type AccessMatrixResult,
  type ActorListResult,
} from '@/fixtures/actor-governance-fixture';

// 'error' = 生产构建下 API 失败的诚实不可用态（R-007）。
export type PanelSource = 'idle' | 'loading' | 'live' | 'fixture' | 'error';

const TENANT_ID = 'sd-default';

export interface ActorWriteResult {
  ok: boolean;
  audit_id?: string;
  binding_status?: string;
  status?: string;
  error?: string;
}

export interface ListActorsOpts {
  role: string;
  q?: string;
  orgCode?: string;
  roleCode?: string;
  status?: string;
}

export interface UseActorGovernanceResult {
  // 「用户与角色」面板
  actorData: Ref<ActorListResult | null>;
  actorSource: Ref<PanelSource>;
  actorError: Ref<string | null>;
  listActors: (opts: ListActorsOpts) => Promise<void>;
  assignRole: (
    role: string,
    externalActorId: string,
    orgCode: string,
    roleCode: string,
    note?: string,
  ) => Promise<ActorWriteResult>;
  revokeRole: (
    role: string,
    externalActorId: string,
    orgCode: string,
    roleCode: string,
    note?: string,
  ) => Promise<ActorWriteResult>;
  setStatus: (
    role: string,
    externalActorId: string,
    status: 'active' | 'disabled',
    note?: string,
  ) => Promise<ActorWriteResult>;
  // 「谁能访问什么」面板
  matrixData: Ref<AccessMatrixResult | null>;
  matrixSource: Ref<PanelSource>;
  matrixError: Ref<string | null>;
  loadAccessMatrix: (role: string) => Promise<void>;
}

export function useActorGovernance(): UseActorGovernanceResult {
  const actorData = ref<ActorListResult | null>(null);
  const actorSource = ref<PanelSource>('idle');
  const actorError = ref<string | null>(null);

  const matrixData = ref<AccessMatrixResult | null>(null);
  const matrixSource = ref<PanelSource>('idle');
  const matrixError = ref<string | null>(null);

  async function listActors(opts: ListActorsOpts): Promise<void> {
    actorSource.value = 'loading';
    actorError.value = null;
    try {
      const payload: Record<string, unknown> = { role: opts.role, tenant_id: TENANT_ID };
      if (opts.q) payload.q = opts.q;
      // org_filter (not org_code): the trusted BFF path overwrites payload.org_code with the
      // caller's own org, which would silently restrict a ROLE_SYSTEM admin to their own org.
      if (opts.orgCode) payload.org_filter = opts.orgCode;
      if (opts.roleCode) payload.role_code = opts.roleCode;
      if (opts.status) payload.status = opts.status;
      const body = await postSkill<ActorListResult>('governance.actor.list', payload);
      if (!body || !Array.isArray(body.items)) throw new Error('payload shape unexpected');
      actorData.value = body;
      actorSource.value = 'live';
    } catch (e) {
      actorError.value = e instanceof Error ? e.message : String(e);
      applyPanelFallback({ data: actorData, source: actorSource }, ACTOR_LIST_FIXTURE, null);
    }
  }

  async function assignRole(
    role: string,
    externalActorId: string,
    orgCode: string,
    roleCode: string,
    note = '',
  ): Promise<ActorWriteResult> {
    try {
      const payload = await postSkill<{ ok?: boolean; audit_id?: string; binding_status?: string }>(
        'governance.actor.role.assign',
        {
          role,
          tenant_id: TENANT_ID,
          external_actor_id: externalActorId,
          target_org_code: orgCode,
          role_code: roleCode,
          confirmed: true,
          note,
          request_id: newRequestId('UI-GOV-ROLE-ASSIGN'),
        },
      );
      return {
        ok: Boolean(payload?.ok ?? true),
        audit_id: payload?.audit_id,
        binding_status: payload?.binding_status,
      };
    } catch (e) {
      return { ok: false, error: e instanceof Error ? e.message : String(e) };
    }
  }

  async function revokeRole(
    role: string,
    externalActorId: string,
    orgCode: string,
    roleCode: string,
    note = '',
  ): Promise<ActorWriteResult> {
    try {
      const payload = await postSkill<{ ok?: boolean; audit_id?: string }>('governance.actor.role.revoke', {
        role,
        tenant_id: TENANT_ID,
        external_actor_id: externalActorId,
        target_org_code: orgCode,
        role_code: roleCode,
        confirmed: true,
        note,
        request_id: newRequestId('UI-GOV-ROLE-REVOKE'),
      });
      return { ok: Boolean(payload?.ok ?? true), audit_id: payload?.audit_id };
    } catch (e) {
      return { ok: false, error: e instanceof Error ? e.message : String(e) };
    }
  }

  async function setStatus(
    role: string,
    externalActorId: string,
    status: 'active' | 'disabled',
    note = '',
  ): Promise<ActorWriteResult> {
    try {
      const payload = await postSkill<{ ok?: boolean; audit_id?: string; status?: string }>(
        'governance.actor.status.set',
        {
          role,
          tenant_id: TENANT_ID,
          external_actor_id: externalActorId,
          status,
          confirmed: true,
          note,
          request_id: newRequestId('UI-GOV-STATUS-SET'),
        },
      );
      return { ok: Boolean(payload?.ok ?? true), audit_id: payload?.audit_id, status: payload?.status };
    } catch (e) {
      return { ok: false, error: e instanceof Error ? e.message : String(e) };
    }
  }

  async function loadAccessMatrix(role: string): Promise<void> {
    matrixSource.value = 'loading';
    matrixError.value = null;
    try {
      const body = await postSkill<AccessMatrixResult>('governance.access_matrix', {
        role,
        tenant_id: TENANT_ID,
      });
      if (!body || !Array.isArray(body.roles)) throw new Error('payload shape unexpected');
      matrixData.value = body;
      matrixSource.value = 'live';
    } catch (e) {
      matrixError.value = e instanceof Error ? e.message : String(e);
      applyPanelFallback({ data: matrixData, source: matrixSource }, ACCESS_MATRIX_FIXTURE, null);
    }
  }

  return {
    actorData,
    actorSource,
    actorError,
    listActors,
    assignRole,
    revokeRole,
    setStatus,
    matrixData,
    matrixSource,
    matrixError,
    loadAccessMatrix,
  };
}
