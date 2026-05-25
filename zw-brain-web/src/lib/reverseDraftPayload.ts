/** 反向编目 wizard → catalog.entry.reverse_draft.* 契约字段映射。 */

export interface ReverseDraftCatalog {
  id: string;
  name: string;
  catalog_code: string;
  schema_ref: string;
  owner?: string;
  status?: string;
  issue?: string;
}

export function mapReverseDraftCatalog(raw: Record<string, unknown>): ReverseDraftCatalog {
  const id = String(raw.id ?? '');
  const name = String(raw.name ?? raw.title ?? id);
  const catalog_code = String(raw.catalog_code ?? raw.legacy_object_ref ?? id);
  const schema_ref = String(
    raw.schema_ref ??
      raw.schema_snapshot_ref ??
      (raw.canonical_resource_id && raw.legacy_object_ref
        ? `${raw.canonical_resource_id}:legacy:${raw.legacy_object_ref}`
        : raw.source_ref ?? catalog_code),
  );
  return { id, name, catalog_code, schema_ref, owner: raw.owner ? String(raw.owner) : undefined, status: raw.status ? String(raw.status) : undefined, issue: raw.issue ? String(raw.issue) : undefined };
}

export function buildReverseDraftSuggestPayload(catalog: ReverseDraftCatalog): Record<string, unknown> {
  return { schema_ref: catalog.schema_ref };
}

export function buildReverseDraftCreatePayload(catalog: ReverseDraftCatalog): Record<string, unknown> {
  return {
    catalog_code: catalog.catalog_code,
    title: catalog.name,
    schema_ref: catalog.schema_ref,
    owner_org_id: catalog.owner || undefined,
  };
}

export function validateReverseDraftCatalog(catalog: ReverseDraftCatalog | null): string | null {
  if (!catalog) return '请先选择待编目目录。';
  if (!catalog.schema_ref.trim()) return '该目录缺少 schema 引用，暂无法发起反向编目。';
  if (!catalog.catalog_code.trim()) return '该目录缺少目录编码，暂无法创建草稿。';
  if (!catalog.name.trim()) return '该目录缺少名称，暂无法创建草稿。';
  return null;
}
