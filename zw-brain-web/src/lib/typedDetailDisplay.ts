/** 分型资源详情 / 目录编制规范字段展示（反馈 5/6）。
 *
 * 后端 catalog.resource_view / catalog.resource.list 已把分型块（typedDetail）与
 * 目录编制规范字段（catalogMeta）+ 共享语义（accessPolicy）投影成机读 dict，本模块只做
 * 「按申请决策分层」的取舍：首屏 = 决策字段（共享/更新/提供方/摘要 + 分型块），
 * 折叠 = 编目字段全集（目录代码/来源/格式/领域 …），一个不漏但不抢首屏。
 */
import type { DetailRow } from '@/lib/detailDisplay';

interface TypedSection {
  title: string;
  rows: { label: string; value: string | null }[];
}
interface TypedDetail {
  kind: string;
  kindLabel: string;
  sections: TypedSection[];
}

function str(v: unknown): string {
  return v === null || v === undefined ? '' : String(v);
}

export interface DisplaySection {
  title: string;
  rows: { label: string; value: string }[];
}

/** 分型块 → DetailPanel 行；value 为 null/'' 时渲染「未提供」诚实空态。 */
export function typedSectionsToRows(typed: TypedDetail | null | undefined): DisplaySection[] {
  if (!typed || !Array.isArray(typed.sections)) return [];
  return typed.sections.map((sec) => ({
    title: sec.title,
    rows: sec.rows.map((r) => ({ label: r.label, value: r.value ?? '' })),
  }));
}

/** 首屏决策字段：共享方式 / 共享条件 / 更新周期 / 提供方 / 摘要（accessPolicy + catalogMeta）。 */
export function decisionRows(
  accessPolicy: Record<string, unknown> | null | undefined,
  catalogMeta: Record<string, unknown> | null | undefined,
): DetailRow[] {
  const ap = accessPolicy ?? {};
  const cm = catalogMeta ?? {};
  const out: { label: string; value: string }[] = [];
  const shareLabel = str(ap.shareTypeLabel) || str(ap.shareType);
  if (shareLabel) out.push({ label: '共享类型', value: shareLabel });
  const shareCond = str(ap.shareCondition);
  if (shareCond) out.push({ label: '共享条件', value: shareCond });
  const openLabel = str(ap.openTypeLabel) || str(ap.openType);
  if (openLabel) out.push({ label: '开放类型', value: openLabel });
  const cycle = str(cm.updateCycleLabel) || str(cm.updateCycle);
  if (cycle) out.push({ label: '更新周期', value: cycle });
  const provider = str(cm.provider) || str(ap.provider);
  if (provider) out.push({ label: '数据提供方', value: provider });
  return out.map((r) => ({ label: r.label, value: r.value, kind: 'text' as const }));
}

/** 折叠编目字段（编制规范全集）：目录名称/代码/分类/来源/格式/领域/版本/发布时间/内部部门。 */
export function compilationRows(catalogMeta: Record<string, unknown> | null | undefined): DetailRow[] {
  const cm = catalogMeta ?? {};
  const out: { label: string; value: string }[] = [];
  const push = (label: string, v: unknown) => {
    const s = str(v);
    if (s) out.push({ label, value: s });
  };
  push('数据资源目录名称', cm.catalogName);
  push('数据资源目录代码', cm.catalogCode);
  push('信息资源格式', str(cm.resourceFormatLabel) || str(cm.resourceFormat));
  push('来源系统', cm.sourceSystem);
  push('内部部门', cm.internalDept);
  push('所属领域', cm.domain);
  // B3（反馈 6.4#5）：旧平台编制规范有「应用场景 / 业务更新周期 / 数据更新周期」三字段，
  // 此前缺位。应用场景独立成行；两个更新周期与首屏「更新周期」决策行不重复（首屏是合并值，
  // 此处是编制规范全集的业务/数据细分）。
  push('应用场景', cm.applicationScenario);
  push('业务更新周期', str(cm.businessUpdateCycleLabel) || str(cm.businessUpdateCycle));
  push('数据更新周期', str(cm.dataUpdateCycleLabel) || str(cm.dataUpdateCycle));
  push('目录版本', cm.catalogVersion);
  push('发布时间', cm.publishedTime);
  return out.map((r) => ({ label: r.label, value: r.value, kind: 'text' as const }));
}

/** 数据资源摘要（单独成块，全文展示）。 */
export function catalogSummary(catalogMeta: Record<string, unknown> | null | undefined): string {
  return str((catalogMeta ?? {}).summary);
}
