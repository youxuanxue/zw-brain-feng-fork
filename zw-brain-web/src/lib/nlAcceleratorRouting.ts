// F7 page-anchor → E1 live skill 映射：NL 面板不再依赖 nl.accelerator.parse 占位 skill。
// 各 anchor 调用已 land 的读/助手 cap，把响应投影为 StructuredAction[]。

import { postSkill, newRequestId } from '@/composables/useApiClient';
import type { NLAcceleratorParseResult, StructuredAction } from '@/fixtures/nl-accelerator-fixture';

// 申请编号提取：Action D 后新铸申请编码为 32 位 hex（与导入单同形）；
// 存量 REQ-* 历史编号继续可解析（用户粘贴旧单号的场景）。
const REQ_PATTERN = /(?:REQ-[A-Z0-9-]+|\b[0-9a-f]{32}\b)/i;

// NL 查询一律用会话当前岗位：原 ANCHOR_ROLE 表把 B1.1/B1.2 强制覆写为
// SECURITY_AUDIT/BUSIAUDIT，D55 收权后会让真实单岗位会话（如平台运维员在外部系统页）
// 被 resolve_trusted_role 拒（403）——后端 policy 才是权限判定单源，前端不替它选角色。

export async function parseNLAcceleratorLive(
  pageAnchor: string,
  query: string,
  role: string,
): Promise<NLAcceleratorParseResult> {
  const effectiveRole = role;
  switch (pageAnchor) {
    case 'P2':
      return parseP2(query, effectiveRole);
    case 'P3':
      return parseP3(query, effectiveRole);
    case 'B1.1':
      return parseB11(query, effectiveRole);
    case 'B1.2':
      return parseB12(query, effectiveRole);
    default:
      throw new Error(`unsupported NL page anchor: ${pageAnchor}`);
  }
}

// ── P2 → search.intent.parse ──────────────────────────────────────────

interface SearchIntentParse {
  intent?: string;
  keywords?: string[];
  missing_fields?: string[];
  recommendation_reason?: string;
  follow_up_questions?: string[];
}

const ZONE_BY_TOPIC: Record<string, string> = {
  营商环境: '营商环境专区',
  治理减负: '治理减负专区',
  民生保障: '民生保障专区',
};

function deriveP2SearchQuery(rawQuery: string, data: SearchIntentParse): string {
  const kws = (data.keywords ?? []).map((k) => String(k).trim()).filter(Boolean);
  if (kws.length) return kws[0];
  return rawQuery.trim();
}

function resolveZoneTopic(searchQuery: string, rawQuery: string): string | null {
  const hay = `${searchQuery} ${rawQuery}`;
  for (const [topic, zone] of Object.entries(ZONE_BY_TOPIC)) {
    if (hay.includes(topic)) return zone;
  }
  return null;
}

// 把一段（智能解析后的或原始的）查询词投影成「搜索」结构化动作。智能解析 200 与
// 降级回落两条路径共用，保证降级路径仍给得出可执行的关键词搜索动作。
function buildP2SearchAction(searchQ: string, rawQuery: string): StructuredAction | null {
  if (!searchQ) return null;
  const zone = resolveZoneTopic(searchQ, rawQuery);
  if (zone) {
    return {
      kind: 'filter',
      label: `搜索：${zone.replace(/专区$/, '')}`,
      target: 'zone',
      payload: { zone, query: zone.replace(/专区$/, '') },
    };
  }
  return {
    kind: 'filter',
    label: `搜索：${searchQ}`,
    target: 'query',
    payload: { query: searchQ },
  };
}

// 找数助手失败时的优雅降级：search.intent.parse 只是「意图增强」，搜索本身不依赖它。
// 当前岗位无该 cap（403）或调用本身失败时，不再把任何错误统统报「解析未命中」，而是
// 直接用用户原始输入产出一个可执行的关键词搜索动作（搜索面始终可用）。403 额外给出
// 「当前岗位无找数助手增强」的诚实提示，区分「无权限」与「真的没解析出动作」。
function degradeP2(query: string, isForbidden: boolean): NLAcceleratorParseResult {
  const raw = query.trim();
  const action = buildP2SearchAction(raw, query);
  const actions = action ? [action] : [];
  const summary = isForbidden
    ? `当前岗位无「找数助手」增强能力；已按关键词「${raw || '（空）'}」直接搜索。`
    : `智能解析暂不可用；已按关键词「${raw || '（空）'}」直接搜索。`;
  return {
    summary,
    // 有可执行搜索动作即 partial（仍可操作、只是少了意图增强）；连查询词都为空才 pending。
    parse_status: actions.length ? 'partial' : 'pending',
    actions,
  };
}

async function parseP2(query: string, role: string): Promise<NLAcceleratorParseResult> {
  let data: SearchIntentParse;
  try {
    data = await postSkill<SearchIntentParse>('search.intent.parse', {
      role,
      query,
      enabled: true,
      request_id: newRequestId('UI-NL-P2'),
    });
  } catch (e) {
    // 无权限岗位（ROLE_SECURITY_AUDIT / 平台运维 / 系统 等）返 403，以及任何其它
    // 调用失败：优雅降级到纯关键词搜索，避免「解析未命中」误导（Bug3）。
    const status = (e as { status?: number } | null)?.status;
    return degradeP2(query, status === 403);
  }
  const actions: StructuredAction[] = [];
  const searchQ = deriveP2SearchQuery(query, data);

  if (data.intent === 'query_application') {
    // 「办申请」导航解体后「我的申请」并入领数据（P4Delivery「我的申请」tab）。
    actions.push({ kind: 'navigate', label: '查看在途申请', target: '#/delivery-exchange' });
  } else if (data.intent === 'register_demand') {
    actions.push({ kind: 'navigate', label: '登记找不到的数据', target: '#/request-flow/supply-demand' });
  } else {
    const action = buildP2SearchAction(searchQ, query);
    if (action) actions.push(action);
  }

  const partial = (data.missing_fields?.length ?? 0) > 0;
  const primary = actions[0]?.label ?? '搜索';
  return {
    summary: data.recommendation_reason ?? `已为你执行「${primary}」`,
    parse_status: partial ? 'partial' : 'ok',
    actions,
  };
}

// ── P3 → request.list / approval.evidence.summarize / application.draft.suggest ──

interface RequestListItem {
  id?: string;
  status?: string;
  submittedAt?: string;
  resourceName?: string;
}

interface ApprovalEvidence {
  recommendation?: string;
  recommended_decision_reason?: string;
  historical_summary?: string;
  bases?: string[];
  application_id?: string;
}

interface DraftSuggest {
  reasoning?: string;
  risk_band?: string;
  missing_fields?: string[];
  suggested_fields?: Record<string, unknown>;
}

function isApprovalQuery(q: string): boolean {
  return /待审|审批|催办|驳回|通过|跟进|几条|REQ-/i.test(q);
}

function isStaleRejectQuery(q: string): boolean {
  return /驳回|未跟进|30\s*天/.test(q);
}

function extractReqId(q: string): string | null {
  const m = q.match(REQ_PATTERN);
  if (!m) return null;
  // REQ-* 历史编号归一大写；hex 编码保持小写（大写会查不到）。
  return m[0].toUpperCase().startsWith('REQ-') ? m[0].toUpperCase() : m[0].toLowerCase();
}

async function parseP3(query: string, role: string): Promise<NLAcceleratorParseResult> {
  const q = query.trim();
  const reqId = extractReqId(q);

  if (isStaleRejectQuery(q) && !reqId) {
    return {
      summary: '识别到批量驳回 / 长期未跟进场景；执行前需人工确认',
      parse_status: 'partial',
      actions: [
        { kind: 'filter', label: '过滤：≥30 天未跟进', target: 'stale_only', payload: { days: 30 } },
        {
          kind: 'draft',
          label: '草拟批量驳回意见（需人工 confirm）',
          target: 'approval.case.decide',
          payload: { decision: 'reject' },
        },
      ],
    };
  }

  if (isApprovalQuery(q)) {
    const list = await postSkill<{ items?: RequestListItem[] }>('request.list', {
      role,
      request_id: newRequestId('UI-NL-P3-LIST'),
    });
    const items = list.items ?? [];
    const pending = items.filter((it) => String(it.status ?? '').includes('pending'));
    const targetId = reqId ?? pending[0]?.id;

    if (/几条|多少|待审/.test(q) && !reqId) {
      return {
        summary: `当前 ${items.length} 条在途，其中 ${pending.length} 条待审批`,
        parse_status: 'ok',
        actions: [
          {
            kind: 'filter',
            label: '只显示「待我审批」',
            target: 'mine_pending',
            payload: { stage: 'pending_review' },
          },
          { kind: 'invoke', label: '刷新申请列表', target: 'request.list', payload: {} },
        ],
      };
    }

    if (/催办/.test(q)) {
      const recent = items[0];
      const label = recent?.resourceName ?? recent?.id ?? '最近提交';
      return {
        summary: recent
          ? `最近 1 条「${label}」可发起催办提醒`
          : '暂无在途申请可催办',
        parse_status: recent ? 'ok' : 'partial',
        actions: recent
          ? [
              { kind: 'filter', label: '定位最近提交', target: 'time_window', payload: { date: 'recent' } },
              {
                kind: 'invoke',
                label: '触发催办通知',
                target: 'request.submit',
                payload: { request_id: recent.id, reminder: true },
              },
            ]
          : [],
      };
    }

    if (targetId) {
      const evidence = await postSkill<ApprovalEvidence>('approval.evidence.summarize', {
        role,
        application_id: targetId,
        enabled: true,
        request_id: newRequestId('UI-NL-P3-EVD'),
      });
      const rec = evidence.recommendation ?? 'return_for_fix';
      const actions: StructuredAction[] = [
        {
          kind: 'navigate',
          label: `查看申请 ${targetId}`,
          target: `#/request-flow/request/${targetId}`,
        },
        {
          kind: 'invoke',
          label: '拉审批详情',
          target: 'approval.view',
          payload: { request_id: targetId },
        },
      ];
      if (rec === 'reject') {
        actions.push({
          kind: 'draft',
          label: '草拟驳回依据',
          target: 'approval.case.decide',
          payload: { decision: 'reject', request_id: targetId },
        });
      }
      return {
        summary:
          evidence.recommended_decision_reason ??
          `审批建议：${rec}；${evidence.historical_summary ?? ''}`.trim(),
        parse_status: 'ok',
        actions,
      };
    }
  }

  const draft = await postSkill<DraftSuggest>('application.draft.suggest', {
    role,
    resource_name: inferResourceName(q),
    applicant_org: '本部门',
    use_case: q,
    enabled: true,
    request_id: newRequestId('UI-NL-P3-DRAFT'),
  });
  const actions: StructuredAction[] = [];
  // 去掉「预填申请草拟字段」假动作：它只有 inferResourceName 字符串猜的资源名、无 resource_id，
  // request.create 调不动；旧 consumeNLAction 只弹「已应用」却什么都没填（撒谎 toast）。真预填是
  // 草稿表单内「补全建议」按钮（request.draft.ai_suggest）。此处仅留 summary（reasoning+风险带）
  // 与缺口提示，NL 面板回归诚实——只摘要、不假装已预填。
  if (draft.missing_fields?.length) {
    actions.push({
      kind: 'filter',
      label: `待补：${draft.missing_fields[0]}`,
      target: 'missing_fields',
      payload: { fields: draft.missing_fields },
    });
  }
  return {
    summary: draft.reasoning ?? `草拟建议已生成（风险 ${draft.risk_band ?? '—'}）`,
    parse_status: (draft.missing_fields?.length ?? 0) > 0 ? 'partial' : 'ok',
    actions,
  };
}

function inferResourceName(q: string): string {
  const stripped = q.replace(/申请|草拟|帮我|请|数据|资源/g, '').trim();
  return stripped.length >= 2 ? stripped.slice(0, 40) : '通用数据资源';
}

// ── B1.1 → audit.event.anomaly / audit.event.statistics / replay ───────

interface AuditAnomalyResult {
  anomalies?: Array<{
    rule?: string;
    severity?: string;
    summary?: string;
    evidence_request_ids?: string[];
    occurrence_count?: number;
  }>;
  scanned?: number;
}

interface AuditStatisticsResult {
  totals?: Record<string, number>;
  bucket?: string;
}

async function parseB11(query: string, role: string): Promise<NLAcceleratorParseResult> {
  const q = query.trim();
  const reqId = extractReqId(q);

  if (reqId) {
    return {
      summary: `已定位申请单据 ${reqId}；可查看完整审计链`,
      parse_status: 'ok',
      actions: [
        { kind: 'navigate', label: '跳到申请详情', target: `#/request-flow/request/${reqId}` },
        {
          kind: 'invoke',
          label: '查审计回放',
          target: 'audit.replay_evidence_chain',
          payload: { request_id: reqId },
        },
      ],
    };
  }

  if (/统计|本周|24\s*h|热点|失败/.test(q)) {
    const bucket = /24\s*h|小时/.test(q) ? 'hour' : /week|周/.test(q) ? 'week' : 'day';
    const stats = await postSkill<AuditStatisticsResult>('audit.event.statistics', {
      role,
      bucket,
      dimension: 'audit_class',
      request_id: newRequestId('UI-NL-B11-STAT'),
    });
    const totals = stats.totals ?? {};
    const totalEvents = Object.values(totals).reduce((a, b) => a + b, 0);
    const failHint = totals.failed ?? totals.error ?? 0;
    return {
      summary:
        failHint > 0
          ? `近 ${bucket === 'hour' ? '24h' : bucket === 'week' ? '本周' : '今日'}审计事件 ${totalEvents} 条，失败 ${failHint} 条`
          : `近 ${bucket === 'hour' ? '24h' : bucket === 'week' ? '本周' : '今日'}审计事件 ${totalEvents} 条；护栏正常`,
      parse_status: 'ok',
      actions: [
        {
          kind: 'filter',
          label: `时间窗口：${bucket}`,
          target: 'time_window',
          payload: { bucket },
        },
        {
          kind: 'invoke',
          label: '刷新统计聚合',
          target: 'audit.event.statistics',
          payload: { bucket, dimension: 'audit_class' },
        },
      ],
    };
  }

  const anomaly = await postSkill<AuditAnomalyResult>('audit.event.anomaly', {
    role,
    top_n: 10,
    request_id: newRequestId('UI-NL-B11-ANO'),
  });
  const list = anomaly.anomalies ?? [];
  const high = list.filter((a) => a.severity === 'high');
  const top = list[0];
  const actions: StructuredAction[] = [
    {
      kind: 'filter',
      label: high.length ? '风险等级：高' : '展示全部异常',
      target: 'risk',
      payload: { level: high.length ? 'high' : 'all' },
    },
  ];
  if (top?.evidence_request_ids?.[0]) {
    actions.push({
      kind: 'invoke',
      label: '查审计回放',
      target: 'audit.replay_evidence_chain',
      payload: { request_id: top.evidence_request_ids[0] },
      detail: top.summary,
    });
  } else {
    actions.push({
      kind: 'invoke',
      label: '重新扫描异常 Top-N',
      target: 'audit.event.anomaly',
      payload: { top_n: 20 },
    });
  }
  return {
    summary: list.length
      ? `扫描 ${anomaly.scanned ?? '—'} 条审计，命中 ${list.length} 条异常${high.length ? `（高风险 ${high.length} 条）` : ''}`
      : `扫描 ${anomaly.scanned ?? '—'} 条审计，未发现异常`,
    parse_status: 'ok',
    actions,
  };
}

// ── B1.2 → package.list + 启发式 IAM 导航 ─────────────────────────────

interface PackageListItem {
  id?: string;
  status?: string;
  slug?: string;
  desc?: string;
}

async function parseB12(query: string, role: string): Promise<NLAcceleratorParseResult> {
  const q = query.trim();

  if (/IAM|鉴权|身份/.test(q)) {
    return {
      summary: 'IAM 鉴权治理请切换到身份治理面板查看近 7 天失败记录',
      parse_status: 'ok',
      actions: [
        {
          kind: 'navigate',
          label: '跳身份治理面板',
          target: '#/integration-admin/iam-governance',
        },
      ],
    };
  }

  const data = await postSkill<{ items?: PackageListItem[] }>('package.list', {
    role,
    request_id: newRequestId('UI-NL-B12'),
  });
  const items = data.items ?? [];
  const pending = items.filter((it) => String(it.status ?? '') === 'pending');
  const faulty = items.filter((it) =>
    ['suspended', 'rejected', 'revoked', 'rolled-back'].includes(String(it.status ?? '')),
  );

  if (/未注册|待审|能力包/.test(q)) {
    return {
      summary: `当前 ${pending.length} 个待审能力包（共 ${items.length} 个注册项）`,
      parse_status: 'ok',
      actions: [
        {
          kind: 'filter',
          label: '状态：待审',
          target: 'trust_level',
          payload: { trust_level: 'untrusted' },
        },
        {
          kind: 'invoke',
          label: '查注册队列',
          target: 'capability.version.review',
          payload: {},
        },
      ],
    };
  }

  if (/故障|异常|接入/.test(q)) {
    return {
      summary: faulty.length
        ? `识别 ${faulty.length} 个异常状态能力包`
        : '当前接入正常，展示最近接入审核记录',
      parse_status: faulty.length ? 'partial' : 'ok',
      actions: [
        {
          kind: 'invoke',
          label: '查最近接入审核',
          target: 'capability.version.review',
          payload: { window_days: 7 },
        },
      ],
    };
  }

  const match = items.find(
    (it) =>
      (it.slug && q.includes(it.slug)) ||
      (it.desc && q.length >= 2 && it.desc.includes(q.slice(0, 6))),
  );
  return {
    summary: match
      ? `命中能力包 ${match.id ?? match.slug ?? '—'}（${match.status ?? '—'}）`
      : `共 ${items.length} 个能力包，${pending.length} 个待审`,
    parse_status: match ? 'ok' : 'partial',
    actions: [
      {
        kind: 'filter',
        label: match ? `定位：${match.slug ?? match.id}` : '状态：待审',
        target: 'package_filter',
        payload: match ? { package_id: match.id } : { status: 'pending' },
      },
    ],
  };
}
