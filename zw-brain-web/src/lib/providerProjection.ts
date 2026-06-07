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
        title: safeRecordTitle(it.title ?? it.field_name ?? it.summary, it.id, '反向编目审核'),
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

/** 供数侧「目录管理 / 资源管理」概览：按生命周期态分桶计数（真实 snapshot 数据派生）。
 *  让供数人进页即看到本部门「编了多少 / 在审多少 / 待发布多少 / 已发布多少」的管理态，
 *  而非只看审批待办（0605 反馈 6.4#8 供数 IA 重排，负责人加注：呈现目录/资源管理情况）。 */
export interface AssetStatusSummary {
  total: number;
  draft: number;
  reviewing: number;
  pendingPublish: number;
  published: number;
  /** 已停用 / 下线 / 过期等非四态活跃流转的兜底计数——保证 total = 各桶之和自洽，
   *  不让「本部门 N 项」配四桶全 0 时出现「另外几项去哪了」的观感矛盾（R-007）。 */
  inactive: number;
}

const _DRAFT = new Set(['draft', '草稿']);
const _REVIEWING = new Set(['pending_review', '审核中', '待审核']);
const _PENDING_PUBLISH = new Set(['approved_pending_publish', '待发布']);
const _PUBLISHED = new Set(['active', '已发布', '已上线', 'published']);

type _ActiveBucket = 'draft' | 'reviewing' | 'pendingPublish' | 'published';

function _bucketStatus(raw: unknown): _ActiveBucket | null {
  const s = String(raw ?? '').trim();
  if (_DRAFT.has(s)) return 'draft';
  if (_REVIEWING.has(s)) return 'reviewing';
  if (_PENDING_PUBLISH.has(s)) return 'pendingPublish';
  if (_PUBLISHED.has(s)) return 'published';
  return null;
}

function _summarize(rows: unknown[]): AssetStatusSummary {
  const out: AssetStatusSummary = { total: 0, draft: 0, reviewing: 0, pendingPublish: 0, published: 0, inactive: 0 };
  for (const row of rows) {
    const it = asRecord(row);
    const bucket = _bucketStatus(it.lifecycle_status ?? it.status);
    out.total += 1;
    // 四态之外（已停用/下线/过期/空）归 inactive，保证 total = 各桶之和（R-007）。
    if (bucket) out[bucket] += 1;
    else out.inactive += 1;
  }
  return out;
}

/** 本部门目录管理概览（来自 provider.catalogs 真实 snapshot）。 */
export function providerCatalogSummary(provider: Record<string, unknown>): AssetStatusSummary {
  const catalogs = Array.isArray(provider.catalogs) ? provider.catalogs : [];
  return _summarize(catalogs);
}

/** 本部门资源管理概览（来自 provider.resources 真实 snapshot）。 */
export function providerResourceSummary(provider: Record<string, unknown>): AssetStatusSummary {
  const resources = Array.isArray(provider.resources) ? provider.resources : [];
  return _summarize(resources);
}
