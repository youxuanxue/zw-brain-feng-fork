/**
 * 资源类型（物化形态）中文标签 — 前端单一事实源（R-019③）。
 *
 * 此前 4 处各自维护 resource_kind→中文 映射且已分叉（ResourceCard service:'服务'、
 * providerProjection service:'接口'、P2CatalogDetail 无 service 键、P2Discovery 同样缺）。
 * 收口到此，全仓统一。
 *
 * 口径权威源 = 后端 zw_brain/domain/resource_kind.py（读路径折叠）
 * + zw_brain/domain/serializers/typed_resource_detail.py KIND_LABELS。
 * D53②：资源类型只支持「库表 / 文件 / API」——文件夹/链接退役（folder/url/link→file）；
 * service 是 API 的历史别名（service→api），统一显示「接口」（与后端 KIND_LABELS 一致，
 * 修正 ResourceCard 旧「服务」分叉）。
 */

/** legacy 同义词 → 收敛后的物化形态（镜像后端 _READ_KIND_FOLD）。 */
const KIND_FOLD: Readonly<Record<string, string>> = {
  folder: 'file',
  url: 'file',
  link: 'file',
  service: 'api',
};

const CANONICAL_KINDS = new Set(['table', 'file', 'api']);

/** 收敛后物化形态 → 中文标签（镜像后端 KIND_LABELS 的 canonical 子集）。 */
const KIND_LABELS: Readonly<Record<string, string>> = {
  table: '库表',
  file: '文件',
  api: '接口',
};

/** 折叠任意 stored resource_kind 到 table/file/api；空/未知 → null（不臆造）。 */
export function canonicalResourceKind(raw: unknown): string | null {
  if (raw === null || raw === undefined) return null;
  const text = String(raw).trim().toLowerCase();
  if (!text) return null;
  const folded = KIND_FOLD[text] ?? text;
  return CANONICAL_KINDS.has(folded) ? folded : null;
}

/**
 * resource_kind → 中文标签（单一事实源）。
 * 未知/空 → 空串（消费面不渲染徽标，不裸出 legacy 英文，守 R12）。
 */
export function resourceKindLabel(raw: unknown): string {
  const kind = canonicalResourceKind(raw);
  return kind ? KIND_LABELS[kind] : '';
}

/** 仅 canonical 三型的标签表（供筛选 chip 等需要遍历键的场景）。 */
export const CANONICAL_KIND_LABELS = KIND_LABELS;
