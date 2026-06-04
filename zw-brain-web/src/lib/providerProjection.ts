/** P5 提供方 snapshot 投影辅助：正式 field_decisions/hookup_reviews/demand_matches
 *  未 land 时，从 catalogs / resources / directAccess 派生可点通列表（仍属真实 seed 数据）。 */

import { containsBareHexId, deriveRecordName, isBareHexId } from './userLanguage';

export interface ProviderRow {
  id: string;
  title: string;
  catalog: string;
  status: string;
  source: 'projection' | 'derived';
}

function asRecord(v: unknown): Record<string, unknown> {
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : {};
}

/** 关联目录名兜底：名缺失或本身是裸 hex id → 「—」，不把 hex id 当目录名展示。 */
function safeCatalogName(...candidates: unknown[]): string {
  for (const c of candidates) {
    const s = String(c ?? '').trim();
    if (s && !isBareHexId(s)) return s;
  }
  return '—';
}

// 一段文本是否「就是一个长裸编号」（≥20 位、无中文/空格的标识符——hex 或大小写
// 混编目录码），即把编码当标题。
const LONG_BARE_CODE_RE = /^[0-9A-Za-z][0-9A-Za-z/_-]{19,}$/;
function isBareCode(s: string): boolean {
  return LONG_BARE_CODE_RE.test(s) && !/[一-鿿]/.test(s);
}

/**
 * 列表标题兜底：真实业务名优先；标题缺失 / 含 hex / 本身是长裸编号 → 用 id
 * 派生「<类别> …末6位」，绝不把编码或 hex 当标题主文本。
 */
function safeRecordTitle(rawTitle: unknown, id: unknown, category: string): string {
  const t = String(rawTitle ?? '').trim();
  if (t && !containsBareHexId(t) && !isBareCode(t)) return t;
  return deriveRecordName('', id, category);
}

export function deriveFieldDecisions(provider: Record<string, unknown>): ProviderRow[] {
  const explicit = Array.isArray(provider.field_decisions) ? provider.field_decisions : [];
  if (explicit.length) {
    return explicit.map((row) => {
      const it = asRecord(row);
      return {
        id: String(it.id ?? ''),
        title: safeRecordTitle(it.title ?? it.field_name ?? it.summary, it.id, '字段审核'),
        catalog: safeCatalogName(it.catalog_name, it.catalog_id),
        status: String(it.status ?? 'pending'),
        source: 'projection' as const,
      };
    });
  }
  const catalogs = Array.isArray(provider.catalogs) ? provider.catalogs : [];
  return catalogs
    .map((c) => asRecord(c))
    .filter((c) => String(c.issue ?? '').trim())
    .map((c) => ({
      id: `catalog-${String(c.id ?? '')}`,
      title: String(c.issue),
      catalog: safeCatalogName(c.name),
      status: 'pending',
      source: 'derived' as const,
    }));
}

export function deriveHookupReviews(provider: Record<string, unknown>): ProviderRow[] {
  const explicit = Array.isArray(provider.hookup_reviews) ? provider.hookup_reviews : [];
  if (explicit.length) {
    return explicit.map((row) => {
      const it = asRecord(row);
      return {
        id: String(it.id ?? it.review_id ?? ''),
        title: safeRecordTitle(it.title ?? it.summary, it.id ?? it.review_id, '挂接审核'),
        catalog: safeCatalogName(it.resource_name, it.catalog_name),
        status: String(it.status ?? 'pending'),
        source: 'projection' as const,
      };
    });
  }
  const direct = asRecord(provider.directAccess);
  const resources = Array.isArray(direct.resources) ? direct.resources : [];
  const fromDirect = resources
    .map((r) => asRecord(r))
    .filter((r) => String(r.status ?? '').includes('待'))
    .map((r) => ({
      id: String(r.resource_code ?? r.id ?? ''),
      title: String(r.title ?? '资源挂接待上报'),
      catalog: String(r.title ?? '—'),
      status: 'pending',
      source: 'derived' as const,
    }));
  if (fromDirect.length) return fromDirect;

  const resList = Array.isArray(provider.resources) ? provider.resources : [];
  return resList
    .map((r) => asRecord(r))
    .filter((r) => String(r.status ?? '').includes('待'))
    .map((r) => ({
      id: String(r.id ?? ''),
      title: `挂接审核：${String(r.name ?? r.id)}`,
      catalog: String(r.type ?? '—'),
      status: 'pending',
      source: 'derived' as const,
    }));
}

export function deriveDemandMatches(provider: Record<string, unknown>): ProviderRow[] {
  const explicit = Array.isArray(provider.demand_matches) ? provider.demand_matches : [];
  if (explicit.length) {
    return explicit.map((row) => {
      const it = asRecord(row);
      return {
        id: String(it.id ?? it.demand_code ?? ''),
        title: safeRecordTitle(it.title, it.id ?? it.demand_code, '供需对接'),
        catalog: safeCatalogName(it.source, it.matched_catalog),
        status: String(it.status ?? 'pending'),
        source: 'projection' as const,
      };
    });
  }
  const direct = asRecord(provider.directAccess);
  const demands = Array.isArray(direct.demands) ? direct.demands : [];
  return demands.map((d) => {
    const it = asRecord(d);
    return {
      id: String(it.demand_code ?? it.id ?? ''),
      title: safeRecordTitle(it.title, it.demand_code ?? it.id, '国家平台需求'),
      catalog: safeCatalogName(it.source),
      status: String(it.status ?? '待受理'),
      source: 'derived' as const,
    };
  });
}

export function deriveObjectionCases(provider: Record<string, unknown>): ProviderRow[] {
  const explicit = Array.isArray(provider.objection_cases) ? provider.objection_cases : [];
  return explicit.map((row) => {
    const it = asRecord(row);
    return {
      id: String(it.id ?? ''),
      title: safeRecordTitle(it.title ?? it.summary, it.id, '异议响应'),
      catalog: safeCatalogName(it.target_type, it.catalog_name),
      status: String(it.status ?? 'pending'),
      source: 'projection' as const,
    };
  });
}

export function providerTodoCounts(provider: Record<string, unknown>): {
  fieldDec: number;
  hookup: number;
  demand: number;
  objection: number;
} {
  return {
    fieldDec: deriveFieldDecisions(provider).length,
    hookup: deriveHookupReviews(provider).length,
    demand: deriveDemandMatches(provider).length,
    objection: deriveObjectionCases(provider).length,
  };
}
