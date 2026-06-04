/** P2 资源发现：本地即时筛选 + 相关性排序（与 data.search 结果形状一致）。 */

export function resourceHaystack(resource: Record<string, unknown>): string {
  return [
    resource.name,
    resource.title,
    resource.desc,
    resource.description,
    resource.provider,
    resource.zone,
    ...(Array.isArray(resource.fields) ? resource.fields : []),
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();
}

export function filterDiscoveryResources(
  resources: Record<string, unknown>[],
  query: string,
): Record<string, unknown>[] {
  const hay = query.trim().toLowerCase();
  if (!hay) return resources;
  return resources.filter((r) => resourceHaystack(r).includes(hay));
}

/** 标题命中优先于描述，专区名最后 —— 避免搜「营商环境」时列表视觉无变化。 */
export function rankDiscoveryResources(
  resources: Record<string, unknown>[],
  query: string,
): Record<string, unknown>[] {
  const hay = query.trim().toLowerCase();
  if (!hay) return resources;
  const score = (r: Record<string, unknown>): number => {
    const name = String(r.name ?? r.title ?? '').toLowerCase();
    const desc = String(r.desc ?? r.description ?? '').toLowerCase();
    const zone = String(r.zone ?? '').toLowerCase();
    if (name.includes(hay)) return 0;
    if (desc.includes(hay)) return 1;
    if (zone.includes(hay)) return 2;
    return 3;
  };
  return [...resources].sort((a, b) => score(a) - score(b));
}

export function mergeDiscoveryResults(
  snapshot: Record<string, unknown>[],
  apiResults: Record<string, unknown>[],
  query: string,
): Record<string, unknown>[] {
  const q = query.trim();
  if (!q) return snapshot;
  const merged = apiResults.length ? apiResults : filterDiscoveryResources(snapshot, q);
  return rankDiscoveryResources(merged, q);
}

/** 资源类型 / 提供部门筛选（反馈 7）。NL 加速器解析结果落入同一筛选状态、与三件套共存。 */
export interface DiscoveryFilters {
  /** 物化形态 kind：table/file/folder/api/url；'' = 全部。 */
  kind: string;
  /** 提供部门名；'' = 全部。 */
  provider: string;
}

export function resourceKind(resource: Record<string, unknown>): string {
  return String(resource.materializationKind ?? resource.resource_kind ?? resource.kind ?? '');
}

export function resourceProvider(resource: Record<string, unknown>): string {
  return String(resource.provider ?? resource.providerName ?? resource.ownerName ?? '');
}

/** 资源类型 + 提供部门筛选；两者可与名称检索组合（先名称 merge，后类型/部门收窄）。 */
export function applyDiscoveryFilters(
  resources: Record<string, unknown>[],
  filters: DiscoveryFilters,
): Record<string, unknown>[] {
  return resources.filter((r) => {
    if (filters.kind && resourceKind(r) !== filters.kind) return false;
    if (filters.provider && resourceProvider(r) !== filters.provider) return false;
    return true;
  });
}

/** 从当前结果集现算 distinct 提供部门（别写死；真实库有什么就给什么）。 */
export function distinctProviders(resources: Record<string, unknown>[]): string[] {
  const seen = new Set<string>();
  for (const r of resources) {
    const p = resourceProvider(r).trim();
    if (p) seen.add(p);
  }
  return Array.from(seen).sort((a, b) => a.localeCompare(b, 'zh-Hans-CN'));
}

/** 现算结果集里实际出现的资源类型（用于只展示有数据的筛选项，不给空筛选）。 */
export function presentKinds(resources: Record<string, unknown>[]): string[] {
  const seen = new Set<string>();
  for (const r of resources) {
    const k = resourceKind(r).trim();
    if (k) seen.add(k);
  }
  return Array.from(seen);
}
