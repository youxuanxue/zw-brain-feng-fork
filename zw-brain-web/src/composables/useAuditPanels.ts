import { ref, type Ref } from 'vue';
import { newRequestId, postSkill } from './useApiClient';
import {
  ACCOUNTABILITY_FIXTURE,
  ANOMALY_FIXTURE,
  REPLAY_FIXTURE,
  STATISTICS_FIXTURE,
  type AuditAccountabilityResult,
  type AuditAnomalyResult,
  type AuditQueryResult,
  type AuditReplayResult,
  type AuditStatisticsResult,
} from '@/fixtures/b11-fixture';

// B1.1 合规与运营 4 面板封装：调用 audit.event.{query,replay,statistics,anomaly,
// accountability} 5 个后端调用（PR #91 ef9b706/58d5587 已 land main）。失败回退
// b11-fixture.ts（同 sd-default 切片，与 P1Workbench useWorkbench 同 pattern）。
// 共享 BFF 客户端（postSkill / newRequestId）抽到 useApiClient.ts。

export type PanelSource = 'idle' | 'loading' | 'live' | 'fixture';

// ---- replay ----

export interface UseReplayResult {
  data: Ref<AuditReplayResult | null>;
  source: Ref<PanelSource>;
  error: Ref<string | null>;
  load: (requestId: string, role?: string) => Promise<void>;
}

export function useAuditReplay(): UseReplayResult {
  const data = ref<AuditReplayResult | null>(null);
  const source = ref<PanelSource>('idle');
  const error = ref<string | null>(null);

  async function load(requestId: string, role = 'ROLE_SECURITY_AUDIT'): Promise<void> {
    source.value = 'loading';
    error.value = null;
    try {
      const payload = await postSkill<AuditReplayResult>('audit.event.replay', {
        role,
request_id: requestId,
        tenant_id: 'sd-default',
      });
      if (!payload || !Array.isArray(payload.items)) throw new Error('payload shape unexpected');
      data.value = payload;
      source.value = 'live';
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
      data.value = REPLAY_FIXTURE;
      source.value = 'fixture';
    }
  }
  return { data, source, error, load };
}

// ---- statistics ----

export interface UseStatisticsResult {
  data: Ref<AuditStatisticsResult | null>;
  source: Ref<PanelSource>;
  error: Ref<string | null>;
  load: (bucket: 'hour' | 'day' | 'week' | 'month', dimension?: string, role?: string) => Promise<void>;
}

export function useAuditStatistics(): UseStatisticsResult {
  const data = ref<AuditStatisticsResult | null>(null);
  const source = ref<PanelSource>('idle');
  const error = ref<string | null>(null);

  async function load(
    bucket: 'hour' | 'day' | 'week' | 'month' = 'day',
    dimension = 'audit_class',
    role = 'ROLE_SECURITY_AUDIT'
  ): Promise<void> {
    source.value = 'loading';
    error.value = null;
    try {
      const payload = await postSkill<AuditStatisticsResult>('audit.event.statistics', {
        role,
bucket,
        dimension,
        tenant_id: 'sd-default',
        request_id: newRequestId('UI-STAT'),
      });
      if (!payload || !Array.isArray(payload.buckets)) throw new Error('payload shape unexpected');
      data.value = payload;
      source.value = 'live';
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
      data.value = STATISTICS_FIXTURE;
      source.value = 'fixture';
    }
  }
  return { data, source, error, load };
}

// ---- anomaly ----

export interface UseAnomalyResult {
  data: Ref<AuditAnomalyResult | null>;
  source: Ref<PanelSource>;
  error: Ref<string | null>;
  load: (topN?: number, minFailure?: number, role?: string) => Promise<void>;
}

export function useAuditAnomaly(): UseAnomalyResult {
  const data = ref<AuditAnomalyResult | null>(null);
  const source = ref<PanelSource>('idle');
  const error = ref<string | null>(null);

  async function load(topN = 20, minFailure = 3, role = 'ROLE_SECURITY_AUDIT'): Promise<void> {
    source.value = 'loading';
    error.value = null;
    try {
      const payload = await postSkill<AuditAnomalyResult>('audit.event.anomaly', {
        role,
tenant_id: 'sd-default',
        top_n: topN,
        min_failure_count: minFailure,
        request_id: newRequestId('UI-ANOM'),
      });
      if (!payload || !Array.isArray(payload.anomalies)) throw new Error('payload shape unexpected');
      data.value = payload;
      source.value = 'live';
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
      data.value = ANOMALY_FIXTURE;
      source.value = 'fixture';
    }
  }
  return { data, source, error, load };
}

// ---- accountability ----

export interface UseAccountabilityResult {
  data: Ref<AuditAccountabilityResult | null>;
  source: Ref<PanelSource>;
  error: Ref<string | null>;
  load: (actor: string, role?: string) => Promise<void>;
}

export function useAuditAccountability(): UseAccountabilityResult {
  const data = ref<AuditAccountabilityResult | null>(null);
  const source = ref<PanelSource>('idle');
  const error = ref<string | null>(null);

  async function load(actor: string, role = 'ROLE_SECURITY_AUDIT'): Promise<void> {
    source.value = 'loading';
    error.value = null;
    try {
      const payload = await postSkill<AuditAccountabilityResult>('audit.event.accountability', {
        role,
actor,
        tenant_id: 'sd-default',
        request_id: newRequestId('UI-ACCT'),
      });
      if (!payload || !Array.isArray(payload.denied_chains)) throw new Error('payload shape unexpected');
      data.value = payload;
      source.value = 'live';
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
      data.value = ACCOUNTABILITY_FIXTURE;
      source.value = 'fixture';
    }
  }
  return { data, source, error, load };
}

// ---- generic query (留给 panel 切换时按 actor / time 自由查) ----

export interface UseQueryResult {
  data: Ref<AuditQueryResult | null>;
  source: Ref<PanelSource>;
  error: Ref<string | null>;
  load: (filter: Record<string, unknown>, role?: string) => Promise<void>;
}

export function useAuditQuery(): UseQueryResult {
  const data = ref<AuditQueryResult | null>(null);
  const source = ref<PanelSource>('idle');
  const error = ref<string | null>(null);

  async function load(filter: Record<string, unknown>, role = 'ROLE_SECURITY_AUDIT'): Promise<void> {
    source.value = 'loading';
    error.value = null;
    try {
      const payload = await postSkill<AuditQueryResult>('audit.event.query', {
        role,
tenant_id: 'sd-default',
        request_id: newRequestId('UI-QRY'),
        ...filter,
      });
      if (!payload || !Array.isArray(payload.items)) throw new Error('payload shape unexpected');
      data.value = payload;
      source.value = 'live';
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
      data.value = { items: [], summary: {
        total: 0, by_audit_class: {}, by_skill: {}, by_actor: {},
        first_occurred_at: null, last_occurred_at: null,
      } };
      source.value = 'fixture';
    }
  }
  return { data, source, error, load };
}
