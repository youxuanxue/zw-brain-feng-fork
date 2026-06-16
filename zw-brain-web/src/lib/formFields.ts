/** 表单填报字段（form-autofill）：类型 + 能力调用 + provenance 视觉映射。
 *
 * 后端 request.create 把可编辑字段装配进 request.formFields（每字段带来源/锁定/状态），
 * 前端 EditableFormPanel 据此渲染四态：待填 / AI建议·待确认 / 自动带出(只读) / 已填(锁定)。
 * 人原地修订 → request.field.update（标 human+locked，此后 autofill/AI 不覆盖、并重跑派生）。
 * 选择器 options → reference.{organ,region,dict}.options（只读带出）。
 */
import { postSkill, newRequestId } from '@/composables/useApiClient';

export type FieldSource = 'human' | 'derived' | 'ai_suggested' | 'empty';
export type FieldKind = 'text' | 'org' | 'region' | 'enum' | 'derived';

export interface FormField {
  key: string;
  label: string;
  kind: FieldKind;
  value: string;
  source: FieldSource;
  locked: boolean;
  state: string;
  stateLabel: string;
  editable: boolean;
  aiSuggestable: boolean;
  dictType?: string | null;
}

export interface RefOption {
  code: string;
  name: string;
  parent_code?: string | null;
  region_code?: string | null;
}

interface SkillEnvelope<T> {
  result?: T;
}

function unwrap<T>(env: SkillEnvelope<T> | T): T {
  if (env && typeof env === 'object' && 'result' in env && (env as SkillEnvelope<T>).result) {
    return (env as SkillEnvelope<T>).result as T;
  }
  return env as T;
}

/** 人原地修订一个字段 → 返回重算后的最新 formFields。 */
export async function updateField(requestId: string, field: string, value: string, role?: string): Promise<FormField[]> {
  const env = await postSkill<SkillEnvelope<{ formFields: FormField[] }>>('request.field.update', {
    request_id: requestId,
    field,
    value,
    role: role ?? '',
    request_id_meta: newRequestId('UI-FIELD'),
  });
  return unwrap(env).formFields ?? [];
}

/** 对草稿空字段生成 AI 建议（标 ai_suggested·待确认）→ 返回最新 formFields。永不自动提交。 */
export async function aiSuggestDraft(requestId: string, role?: string): Promise<FormField[]> {
  const env = await postSkill<SkillEnvelope<{ formFields: FormField[] }>>('request.draft.ai_suggest', {
    request_id: requestId,
    role: role ?? '',
    request_id_meta: newRequestId('UI-AISUGGEST'),
  });
  return unwrap(env).formFields ?? [];
}

/** 枚举字段下拉 options（pub_dict KIND 分组）。 */
export async function fetchDictOptions(dictType: string): Promise<RefOption[]> {
  const env = await postSkill<SkillEnvelope<{ options: RefOption[] }>>('reference.dict.options', {
    dict_type: dictType,
    request_id_meta: newRequestId('UI-DICT'),
  });
  return unwrap(env).options ?? [];
}

/** 区划逐级下钻 options。 */
export async function fetchRegionOptions(parentCode: string): Promise<RefOption[]> {
  const env = await postSkill<SkillEnvelope<{ options: RefOption[] }>>('reference.region.options', {
    parent_code: parentCode,
    request_id_meta: newRequestId('UI-REGION'),
  });
  return unwrap(env).options ?? [];
}

/** 机构搜索分页结果（18750 机构无法靠扁平下拉，必须关键词 + 分页）。 */
export interface OrganPage {
  options: RefOption[];
  total: number;
  offset: number;
  limit: number;
}

/** 机构搜索分页：keyword 模糊匹名称/编码 + 可选区划过滤 + offset/limit，DB 层切片。
 *  入参用 reference_region_code，避开后端框架注入的 actor 上下文同名键（org_code/region_code）。 */
export async function fetchOrganOptions(
  regionCode = '',
  keyword = '',
  offset = 0,
  limit = 20,
): Promise<OrganPage> {
  const env = await postSkill<SkillEnvelope<OrganPage>>('reference.organ.options', {
    reference_region_code: regionCode,
    keyword,
    offset,
    limit,
    request_id_meta: newRequestId('UI-ORGAN'),
  });
  const r = unwrap(env);
  return { options: r.options ?? [], total: r.total ?? 0, offset: r.offset ?? offset, limit: r.limit ?? limit };
}

/** provenance 来源 → 视觉 tone class（四态色）。 */
export function sourceTone(source: FieldSource): string {
  switch (source) {
    case 'human':
      return 'ff-human';
    case 'derived':
      return 'ff-derived';
    case 'ai_suggested':
      return 'ff-ai';
    default:
      return 'ff-empty';
  }
}
