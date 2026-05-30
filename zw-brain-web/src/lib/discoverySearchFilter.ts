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
