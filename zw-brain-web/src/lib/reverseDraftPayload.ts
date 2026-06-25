/** 反向编目 wizard → catalog.entry.reverse_draft.* 契约字段映射。 */

export interface ReverseDraftCatalog {
  id: string;
  name: string;
  catalog_code: string;
  schema_ref: string;
  owner?: string;
  ownerOrgId?: string;
  status?: string;
  issue?: string;
}

/** suggest 后端（reverse_draft_suggest.build_field_suggestions）逐字段输出行。 */
export interface ReverseFieldSuggestion {
  field_en: string;
  field_cn: string;
  confidence: string; // green | yellow | orange
  source: string; // data-standard | comment | pii-pattern | llm-stub
  data_type: string;
  sensitive_level: string; // '1'..'4'，PII 定密由后端 reverse_draft_suggest.py:124-128 给出
}

/** 用户在候选表勾选/修订后、随 create 入库的确认行（含人改后的中文名/敏感级）。 */
export interface ReverseFieldDecision {
  field_en: string;
  field_cn: string;
  sensitive_level: string;
  source: string;
  selected: boolean;
}

/** 把 invokeActionStub 返回的 res.data 解析成可勾选/可改的候选表。 */
export function parseFieldSuggestions(data: unknown): ReverseFieldSuggestion[] {
  if (!data || typeof data !== 'object') return [];
  const raw = (data as Record<string, unknown>).fields;
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((r): r is Record<string, unknown> => Boolean(r) && typeof r === 'object')
    .map((r) => ({
      field_en: String(r.field_en ?? ''),
      field_cn: String(r.field_cn ?? ''),
      confidence: String(r.confidence ?? 'orange'),
      source: String(r.source ?? 'llm-stub'),
      data_type: String(r.data_type ?? ''),
      sensitive_level: String(r.sensitive_level ?? '1'),
    }))
    .filter((r) => r.field_en);
}

/** 标题建议（title_suggestion.title），suggest 返回时回填到目录名草稿。 */
export function parseTitleSuggestion(data: unknown): string {
  if (!data || typeof data !== 'object') return '';
  const ts = (data as Record<string, unknown>).title_suggestion;
  if (!ts || typeof ts !== 'object') return '';
  return String((ts as Record<string, unknown>).title ?? '').trim();
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
  return {
    id,
    name,
    catalog_code,
    schema_ref,
    owner: raw.owner ? String(raw.owner) : undefined,
    ownerOrgId: raw.owner_org_id ? String(raw.owner_org_id) : undefined,
    status: raw.status ? String(raw.status) : undefined,
    issue: raw.issue ? String(raw.issue) : undefined,
  };
}

export function buildReverseDraftSuggestPayload(catalog: ReverseDraftCatalog): Record<string, unknown> {
  return { schema_ref: catalog.schema_ref };
}

export function buildReverseDraftCreatePayload(
  catalog: ReverseDraftCatalog,
  decisions?: ReverseFieldDecision[],
): Record<string, unknown> {
  // 仅把用户确认勾选的候选随 create 持久化（catalog_entry.py:367 接收为
  // draft_field_suggestions；未勾选的不入库，避免把噪声字段写进草稿）。
  const draft_field_suggestions = (decisions ?? [])
    .filter((d) => d.selected && d.field_en.trim())
    .map((d) => ({
      field_en: d.field_en,
      field_cn: d.field_cn,
      sensitive_level: d.sensitive_level,
      source: d.source,
    }));
  return {
    catalog_code: catalog.catalog_code,
    title: catalog.name,
    schema_ref: catalog.schema_ref,
    owner_org_id: catalog.ownerOrgId || undefined,
    draft_field_suggestions,
  };
}

export function validateReverseDraftCatalog(catalog: ReverseDraftCatalog | null): string | null {
  if (!catalog) return '请先选择待编目目录。';
  if (!catalog.schema_ref.trim()) return '该目录缺少 schema 引用，暂无法发起反向编目。';
  if (!catalog.catalog_code.trim()) return '该目录缺少目录编码，暂无法创建草稿。';
  if (!catalog.name.trim()) return '该目录缺少名称，暂无法创建草稿。';
  return null;
}
