/** 详情页字段展示：与 statusLabels / auditDisplay 对齐，供 DetailPanel 单一消费。 */

import { formatActorLabel } from '@/lib/auditDisplay';
import { formatTodoStatus, todoStatusTone } from '@/lib/statusLabels';

export type DetailRowKind = 'text' | 'status' | 'tech' | 'actor';

export interface DetailRow {
  label: string;
  value: string;
  kind?: DetailRowKind;
  /** 主展示与原始值不同时，在下方展示原始技术标识 */
  raw?: string;
  state?: string;
  source?: string;
}

const STATUS_LABELS = new Set(['当前状态', '状态', '处理状态']);

const ACTOR_LABELS = new Set(['申请人', '关注对象', '提供方']);

const TECH_HINT = /^(user:|REQ-|res-|cat-|AE-)/;

export function inferDetailRow(label: string, value: string): DetailRow {
  const v = String(value ?? '').trim();
  if (!v) return { label, value: '—', kind: 'text' };

  if (STATUS_LABELS.has(label) || label.endsWith('状态')) {
    return { label, value: formatTodoStatus(v), kind: 'status', raw: v };
  }
  if (ACTOR_LABELS.has(label) || label.includes('申请人')) {
    const short = formatActorLabel(v);
    return {
      label,
      value: short,
      kind: 'actor',
      raw: short !== v ? v : undefined,
    };
  }
  if (TECH_HINT.test(v) || v.includes('[bypass]')) {
    return { label, value: formatActorLabel(v), kind: 'actor', raw: v };
  }
  return { label, value: v, kind: 'text' };
}

export function mapDetailRows(
  rows: { label: string; value: string; state?: string; source?: string }[]
): DetailRow[] {
  return rows.map((r) => ({
    ...inferDetailRow(r.label, r.value),
    state: r.state,
    source: r.source,
  }));
}

export function statusToneForRow(row: DetailRow): string {
  if (row.kind !== 'status') return '';
  return todoStatusTone(row.raw ?? row.value);
}
