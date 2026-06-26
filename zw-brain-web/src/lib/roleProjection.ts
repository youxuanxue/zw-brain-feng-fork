/**
 * 角色投影层 — 「办共享申请」按当前岗位拆成三个清晰视图（缺陷 1）。
 * （缺陷 2 角色待办语义与计数 = 后端 workbench_backlog_projection 机制单源，前端不自算。）
 *
 * 客户试用反馈（0604，业务方试用反馈）：「是看我的已办？还是我的申请？我的授权，里面的数据没分角色，
 * 建议分开」。截图实证：不同角色视角的单据混在一张表里。
 *
 * 乔布斯裁决：一个视图只回答一个问题 ——
 *   - 我的申请 (mine)   ：我作为需方发起的（草稿 / 在途 / 已办结）
 *   - 待我办理 (todo)   ：按我的角色码该我处理的（审核 / 审批 / 受理）
 *   - 我的授权 (grants) ：我已获得的授权与凭据状态
 *
 * 与平行三组边界：
 *   - 第二组（流程收口）：待办「可点可办 + 真实库现算机制」；本层只产**投影口径**（哪类进哪视图、
 *     按 status 分桶），不重做机制。
 *   - 第一组（用户语言层）：hex 派生名 / 时间格式 / 术语映射渲染规则；本层不渲染、只分类。
 *   - 用途脏值降级走 dataQuality.ts（缺陷 3）；本层只负责申请/授权视图分流。
 *
 * 计数口径**只读快照投影**（snapshot.requests / approvals + provider 队列），不裸 SQL、
 * 不在页内 filter（避免漂移）。requests/approvals 投影来自 DB 单一事实源
 * （zw_brain/domain/discovery_snapshot_projection.py），空库 → 诚实空。
 */

import type { Snapshot } from '@/composables/useSnapshot';
import { displayPurpose } from '@/lib/dataQuality';
import { deriveRecordName, formatTime } from '@/lib/userLanguage';

// status 分桶（口径单一来源）。三视图据此把同一批真实导入单分流，不再一锅炖。
// 草稿 / 在途 / 已办结 = 「我的申请」生命周期三段；授权态 = 「我的授权」。
const DRAFT_STATUSES = new Set(['draft', 'need-fix']);
const INFLIGHT_STATUSES = new Set([
  'submitted',
  'pending',
  'under_review',
  'in_review',
  'pending_review',
  'dept_approved',
  'change_pending',
  'supplementing',
]);
const CLOSED_STATUSES = new Set(['approved', 'rejected', 'withdrawn', 'expired', 'revoked']);
// 授权态（「我的授权」视图）：已授权 / 生效 / 暂停 / 到期 —— 凭据生命周期。
const GRANT_STATUSES = new Set(['granted', 'effective', 'suspended', 'expired']);

export interface RequestCard {
  id: string;
  resource: string;
  purpose: string;
  purposeDirty: boolean;
  status: string;
  submittedAt: string;
  isLegacyImport: boolean;
  // 「我的申请」按个人 id 判定（后端 enrich_requests_snapshot 现算：payload.applicant ==
  // 当前登录个人 → mine=true）。前端只读此诚实信号、不自算身份。详见后端 _record_to_request_card。
  mine: boolean;
}

export type RequestBucket = 'draft' | 'inflight' | 'closed' | 'grant' | 'other';

function asRecord(v: unknown): Record<string, unknown> {
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : {};
}

function normStatus(s: unknown): string {
  return String(s ?? '').trim().toLowerCase();
}

/** 申请记录 → 视图卡（用途经 dataQuality 降级，来源诚实标识透传）。 */
export function toRequestCard(raw: unknown): RequestCard {
  const it = asRecord(raw);
  const purposeView = displayPurpose(
    (it.purpose as string | undefined) ?? '',
  );
  const id = String(it.id ?? '');
  return {
    id,
    // 资源名缺失 / 裸 hex（resource_id 回落）→ 派生「数据资源 …末6位」（第一组渲染规则）。
    resource: deriveRecordName(it.resourceName ?? it.resource_id, it.resource_id ?? id, '数据资源'),
    purpose: purposeView.text,
    purposeDirty: purposeView.dirty || Boolean(it.purposeDirty),
    status: String(it.status ?? ''),
    // 裸 ISO（含微秒）→ 本地化 YYYY-MM-DD HH:mm（第一组渲染规则）。
    submittedAt: formatTime(it.submittedAt),
    isLegacyImport: Boolean(it.isLegacyImport),
    mine: Boolean(it.mine),
  };
}

/** 申请落到哪个生命周期桶（三视图分流口径单源）。 */
export function bucketForRequest(raw: unknown): RequestBucket {
  const st = normStatus(asRecord(raw).status);
  if (GRANT_STATUSES.has(st)) return 'grant';
  if (DRAFT_STATUSES.has(st)) return 'draft';
  if (INFLIGHT_STATUSES.has(st)) return 'inflight';
  if (CLOSED_STATUSES.has(st)) return 'closed';
  return 'other';
}

function requests(snapshot: Snapshot | null): unknown[] {
  return (snapshot?.requests as unknown[] | undefined) ?? [];
}

// ── 视图 1：我的申请 ─────────────────────────────────────────────────────
/** 我**本人提交**的申请（draft/inflight/closed），授权态归「我的授权」不重复出现。
 *
 * mine 由后端按个人 id 现算（payload.applicant == 当前登录个人，M5）。修此前 myRequests 只按
 * 状态分桶、不按人过滤——任何角色「我的申请」里都躺着全部门的单（客户 0604 反馈的下半截）。
 * 现按 mine 收口到本人。注意：快照 requests 经后端部门收口后，含「本部门作为提供方的入站单」
 * （别部门申请本部门数据），那些 mine=false、不属「我的申请」，归审批/受理队列。 */
export function myRequests(snapshot: Snapshot | null): RequestCard[] {
  return requests(snapshot)
    .filter((r) => asRecord(r).mine === true && bucketForRequest(r) !== 'grant')
    .map(toRequestCard);
}

// ── 视图 3：我的授权 ─────────────────────────────────────────────────────
/** 我已获得的授权（granted/effective/suspended/expired），含凭据态（凭据诚实化承 D47）。
 *
 * 与 myRequests 对称按 mine 收口到本人：快照 requests 经后端部门收口后，含同部门他人的授权与
 * 「本部门作为提供方的入站单」（别部门申请本部门数据），那些 mine=false、不属「我的授权」，否则
 * 用户点「查看凭据」会进到不属于自己的页面 = 越权可见（客户 0604 反馈下半截，承 myRequests 口径）。 */
export function myGrants(snapshot: Snapshot | null): RequestCard[] {
  return requests(snapshot)
    .filter((r) => asRecord(r).mine === true && bucketForRequest(r) === 'grant')
    .map(toRequestCard);
}

// 注：角色→待办语义与计数已下沉后端 workbench_backlog_projection（机制单源，真实库现算）；
// 前端不再自算待办计数。本层只保留三视图分流。语义定义见
// docs/decisions/role-projection-views-business-review-package.md（D28，pending 签字）。
