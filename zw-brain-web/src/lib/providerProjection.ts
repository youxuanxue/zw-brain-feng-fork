/** P5 提供方 snapshot 投影辅助：正式 field_decisions/hookup_reviews/demand_matches
 *  未 land 时，从 catalogs / resources / directAccess 派生可点通列表（仍属真实 seed 数据）。 */

import { displayRecordName, isBareHexId } from './userLanguage';
import { resourceKindLabel } from './resourceKind';

export interface ProviderRow {
  id: string;
  title: string;
  catalog: string;
  status: string;
  source: 'projection' | 'derived';
  target_resource_hint?: string;
  /** D57⑨/R10：挂接审核被审登记信息（去盲批）——真实登记字段，缺省诚实留空。 */
  detail?: {
    kindLabel: string;
    owner: string;
    sourceRef: string;
    desc: string;
    shareTypeLabel: string;
    fieldCount: number;
  };
}

function asRecord(v: unknown): Record<string, unknown> {
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : {};
}

/** 关联目录名兜底：取首个真实业务名；候选本身是裸 hex / 裸编码 → 经 displayRecordName
 *  降级为「未命名目录（编码 …末6位）」，不把 hex id / org-code 当目录名直出（R12）。 */
function safeCatalogName(...candidates: unknown[]): string {
  for (const c of candidates) {
    const s = String(c ?? '').trim();
    if (s && !isBareHexId(s)) return displayRecordName(s, s, '目录');
  }
  return '—';
}

/**
 * 列表标题兜底：真实业务名优先；标题缺失 / 名==编码 / 含 hex / 本身是裸 id / 裸机构编码
 * → 经 displayRecordName 降级为「未命名{类别}（编码 …末6位）」，绝不把编码或 hex 当标题主文本。
 */
function safeRecordTitle(rawTitle: unknown, id: unknown, category: string): string {
  return displayRecordName(rawTitle, id, category);
}

export function deriveFieldDecisions(provider: Record<string, unknown>): ProviderRow[] {
  const explicit = Array.isArray(provider.field_decisions) ? provider.field_decisions : [];
  if (explicit.length) {
    return explicit.map((row) => {
      const it = asRecord(row);
      return {
        id: String(it.id ?? ''),
        title: safeRecordTitle(it.title ?? it.field_name ?? it.summary, it.id, '反向编目审核'),
        // 部门审被审内容（D57⑧ 去盲批）：责任单位中文名（后端 ReferenceService 解析，
        // 缺则回落 org id 诚实展示）；旧 catalog_name 键保留兜底。
        catalog: safeCatalogName(it.owner, it.catalog_name, it.catalog_id),
        status: String(it.status ?? 'pending'),
        source: 'projection' as const,
        detail: {
          kindLabel: '',
          owner: String(it.owner ?? it.owner_org_id ?? ''),
          sourceRef: '',
          desc: '',
          shareTypeLabel: '',
          fieldCount: Number(it.field_count ?? 0) || 0,
        },
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
        // title=被审资源名（「关联资源」列）；catalog=所属目录名（D57⑨/R10 投影补
        // catalog_name 后不再恒「—」，仍缺时回落 resource_name 再兜「—」）。
        title: safeRecordTitle(it.title ?? it.resource_name ?? it.summary, it.id ?? it.review_id, '挂接审核'),
        catalog: safeCatalogName(it.catalog_name, it.resource_name),
        status: String(it.status ?? 'pending'),
        source: 'projection' as const,
        // D57⑨/R10：被审登记信息透传（后端 _asset_to_hookup_review 单源），审核者行内可见。
        detail: {
          kindLabel: String(it.kind_label ?? ''),
          owner: String(it.owner ?? ''),
          sourceRef: String(it.source_ref ?? ''),
          desc: String(it.desc ?? ''),
          shareTypeLabel: String(it.share_type_label ?? ''),
          fieldCount: Number(it.field_count ?? 0) || 0,
        },
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
        target_resource_hint: String(it.target_resource_hint ?? it.targetResourceHint ?? ''),
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
      target_resource_hint: String(it.target_resource_hint ?? it.targetResourceHint ?? ''),
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
// pending_platform_review（平台审核中，反向编目部门审过/正向编制平台档）也是「审核中」桶——
// 漏它会让该态泄漏英文裸串（破 R12）且被误计进 inactive 桶（与「本部门 N 项」配不上）。
const _REVIEWING = new Set([
  'pending_review',
  'pending_platform_review',
  '审核中',
  '待审核',
  '平台审核中',
]);
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

export function providerLifecycleBucket(raw: unknown): _ActiveBucket | null {
  return _bucketStatus(raw);
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

// ── 供数侧目录/资源「管理清单」行投影（T9）──────────────────────────────────
// 概览卡只算计数；清单页要逐行展示（名称/代码/提供方/生命周期/查看）。同源于
// provider.catalogs / provider.resources 真实 snapshot，与概览卡口径一致（_bucketStatus）。

const _BUCKET_LABEL: Record<_ActiveBucket, string> = {
  draft: '草稿',
  reviewing: '审核中',
  pendingPublish: '待发布',
  published: '已发布',
};
// 与桶标签同义但更具体的机器态 → 中文（pending_platform_review 桶=审核中，但展示词
// 要区分「平台审核中」，与后端 resource_lifecycle.lifecycle_label 同口径，前端零词表对齐）。
const _SPECIFIC_LABEL: Record<string, string> = {
  pending_platform_review: '平台审核中',
};
// 非四态机器值 → 中文（已是中文则原样透传；都不命中诚实回落原值/「—」）。
const _INACTIVE_LABEL: Record<string, string> = {
  suspended: '已停用',
  retired: '已退役',
  expired: '已过期',
  offline: '已下线',
  rejected: '已驳回',
  revoked: '已撤销',
};

/** 生命周期态 → 中文展示标签（R12 前端零词表口径，与概览卡分桶同源）。 */
function _statusLabel(raw: unknown): string {
  const s = String(raw ?? '').trim();
  // 具体态优先（平台审核中 vs 审核中），再回落桶标签。
  if (_SPECIFIC_LABEL[s]) return _SPECIFIC_LABEL[s];
  const bucket = _bucketStatus(s);
  if (bucket) return _BUCKET_LABEL[bucket];
  if (/[一-鿿]/.test(s)) return s; // 已是中文（snapshot 部分行直接落中文态）
  return _INACTIVE_LABEL[s.toLowerCase()] ?? (s || '—');
}

export function providerLifecycleLabel(raw: unknown): string {
  return _statusLabel(raw);
}

/** 行内动作（C：草稿续编/提交审核）。href=跳转链接；actionId=点击调能力（由页面承接）。 */
export interface ProviderRowAction {
  label: string;
  href?: string;
  actionId?: string;
  danger?: boolean;
}

/** J2 供数脊柱 timeline 段（F；与 PhaseTrack TimelineStep 同形，后端现算）。 */
export interface ProviderTimelineStep {
  stage: string;
  status: string;
  label: string;
  holder?: string;
}

export interface ProviderAssetRow {
  id: string;
  name: string;
  /** 目录：数据资源目录代码；资源：所属目录代码。 */
  code: string;
  /** 提供方（org 名优先，无映射诚实回落 org id）。 */
  owner: string;
  /** 中文生命周期态。 */
  status: string;
  /** 状态附注（审核理由回显：退回补证理由或驳回终止理由；驳回为终态，无则空）。 */
  statusNote?: string;
  /** 资源物化形态中文标签（仅资源行）。 */
  kind?: string;
  /** 行内「查看」跳转（复用既有详情路由）。 */
  viewHref: string;
  /** 行内动作（C：草稿行加「继续编辑」+「提交审核」；非草稿行为空）。 */
  actions?: ProviderRowAction[];
  /** J2 供数脊柱（F）：生命周期 timeline 段（后端现算；支线态/未知为空数组）。 */
  timeline?: ProviderTimelineStep[];
  /** 支线态（驳回/退役）中文标注——无 stepper 时诚实说明（F）。 */
  lifecycleNote?: string;
}

function asTimeline(raw: unknown): ProviderTimelineStep[] {
  if (!Array.isArray(raw)) return [];
  return raw.map((s) => {
    const it = asRecord(s);
    return {
      stage: String(it.stage ?? ''),
      status: String(it.status ?? ''),
      label: String(it.label ?? ''),
      holder: String(it.holder ?? ''),
    };
  });
}

/** 本部门「已编目目录」管理清单（按生命周期浏览全部，T9）。 */
export function providerCatalogRows(provider: Record<string, unknown>): ProviderAssetRow[] {
  const catalogs = Array.isArray(provider.catalogs) ? provider.catalogs : [];
  return catalogs.map((row) => {
    const it = asRecord(row);
    const code = String(it.catalog_code ?? it.id ?? '');
    // 展示码优先业务码（数据资源目录代码 DRC-…，T3②），缺则回落内部码；跳转仍用内部码（路由键）。
    const displayCode = String(it.data_catalog_code ?? '') || code;
    // C：草稿行（lifecycle=draft）给行内「继续编辑」（带 ?code= 续编向导）+「提交审核」（调能力）。
    // 后端 _update_catalog_entry / submit_review 早已支持续编，原本纯 UI 缺入口（draft 行只读「查看」）。
    const isDraft = String(it.lifecycle_status ?? it.status ?? '') === 'draft';
    const actions: ProviderRowAction[] = isDraft && code
      ? [
          { label: '继续编辑', href: `#/provider/wizard/inline-catalog?code=${encodeURIComponent(code)}` },
          { label: '提交审核', actionId: code },
        ]
      : [];
    return {
      id: String(it.id ?? ''),
      name: safeRecordTitle(it.name ?? it.title, it.id, '目录'),
      code: displayCode || '—',
      owner: String(it.owner ?? it.owner_org_id ?? '—'),
      status: _statusLabel(it.status ?? it.lifecycle_status),
      // 审核理由回显（return_for_fix/reject 落 summary → 投影 review_return_reason）；
      // 目录「驳回」为终态枪毙、无重提路径，理由作终止凭据展示。
      statusNote: String(it.review_return_reason ?? '') ? `驳回理由：${String(it.review_return_reason)}` : '',
      // D63 档 B：供数侧「查看」指向独立供数详情路由（供数管理视角，复用消费组件、route.path 判模式；
      // 走供数 shell 角色门，业务运营员不再被弹回工作台）。
      viewHref: code ? `#/provider/catalog/${encodeURIComponent(code)}` : '',
      actions,
      timeline: asTimeline(it.statusTimeline),
      lifecycleNote: String(it.lifecycleNote ?? ''),
    };
  });
}

/** 本部门「已挂接资源」管理清单（按生命周期浏览全部，T9）。 */
export function providerResourceRows(provider: Record<string, unknown>): ProviderAssetRow[] {
  const resources = Array.isArray(provider.resources) ? provider.resources : [];
  return resources.map((row) => {
    const it = asRecord(row);
    const id = String(it.id ?? it.resource_code ?? '');
    const kind = String(it.resource_kind ?? '');
    return {
      id,
      name: safeRecordTitle(it.name ?? it.title, it.id, '资源'),
      code: String(it.catalog_code ?? '—'),
      owner: String(it.owner ?? it.owner_org_id ?? '—'),
      status: _statusLabel(it.lifecycle_status ?? it.status),
      // 审核理由回显（return_for_fix 落 summary → 投影 review_return_reason）。
      statusNote: String(it.review_return_reason ?? '') ? `驳回理由：${String(it.review_return_reason)}` : '',
      // 单源 resourceKindLabel（lib/resourceKind.ts）；未知/空 → '—'（管理清单保留占位）。
      kind: resourceKindLabel(kind) || '—',
      // D63 档 B：供数侧「查看」指向独立供数详情路由 /provider/resource/:id（供数管理视角，复用消费
      // 组件、route.path 判模式）；走供数 shell 角色门，消除心智错配 + 业务运营员被弹回工作台的断点。
      viewHref: id ? `#/provider/resource/${encodeURIComponent(id)}` : '',
      timeline: asTimeline(it.statusTimeline),
      lifecycleNote: String(it.lifecycleNote ?? ''),
    };
  });
}
