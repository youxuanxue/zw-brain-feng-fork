/** 目录在线编制 / 资源注册 字段字典（单一事实源，B1/B2/B3 防漂移）。
 *
 * 乔布斯原则——一处定义，两处引用：
 *  - 采集端（P5InlineCatalogWizard / P5HookupSubmitWizard）按本字典渲染表单、组 summary_json；
 *  - 详情端（catalog_service.catalog_meta / typed_resource_detail / typedDetailDisplay）按
 *    **同一组 summary_json 键** 投影回显。键名漂移即字段在录入后「消失」，故收口到此。
 *
 * R12（段 24）：UI 只见 `label`（业务化中文），裸 summary_json 键名（`source_system`/
 * `shared_type` 等）只在 payload 里，绝不进 DOM 文本。
 *
 * 枚举码与后端 catalog_service._SHARE_TYPE_LABELS / _OPEN_TYPE_LABELS / _UPDATE_CYCLE_LABELS /
 * _RESOURCE_FORMAT_LABELS 同口径（旧平台 dsp_catalog 编制规范枚举）。
 */

export interface SelectOption {
  value: string;
  label: string;
}

/** 共享类型（dsp_catalog shared_type 1/2/3）。 */
export const SHARE_TYPE_OPTIONS: SelectOption[] = [
  { value: '1', label: '无条件共享' },
  { value: '2', label: '有条件共享' },
  { value: '3', label: '不予共享' },
];

/** 开放类型（dsp_catalog open_type 1/2/3）。 */
export const OPEN_TYPE_OPTIONS: SelectOption[] = [
  { value: '1', label: '无条件开放' },
  { value: '2', label: '有条件开放' },
  { value: '3', label: '不予开放' },
];

/** 共享方式（旧平台 shared_way：接口 / 库表 / 文件）。 */
export const SHARE_WAY_OPTIONS: SelectOption[] = [
  { value: 'api', label: '接口' },
  { value: 'table', label: '库表' },
  { value: 'file', label: '文件' },
];

/** 业务/数据更新周期（dsp_catalog update_cycle 1–9）。 */
export const UPDATE_CYCLE_OPTIONS: SelectOption[] = [
  { value: '1', label: '实时' },
  { value: '2', label: '每日' },
  { value: '3', label: '每周' },
  { value: '4', label: '每月' },
  { value: '5', label: '每季度' },
  { value: '6', label: '每半年' },
  { value: '7', label: '每年' },
  { value: '8', label: '不定期' },
  { value: '9', label: '不更新' },
];

/** 信息资源格式（dsp_catalog resource_format 常见档）。 */
export const RESOURCE_FORMAT_OPTIONS: SelectOption[] = [
  { value: '0100', label: '结构化数据' },
  { value: '0200', label: '库表' },
  { value: '0300', label: '非结构化数据' },
  { value: '0310', label: '文件' },
  { value: '0400', label: '接口' },
];

/** 数据提供方式（旧平台 data_resource：周期提供 / 一次性提供）。 */
export const DATA_PROVISION_OPTIONS: SelectOption[] = [
  { value: 'periodic', label: '周期提供' },
  { value: 'one_time', label: '一次性提供' },
];

/** 信息项类型（旧平台 data_resource_table_column 字段类型，r3 截图枚举）。 */
export const ITEM_TYPE_OPTIONS: SelectOption[] = [
  { value: 'C', label: '字符串型' },
  { value: 'N', label: '数值型' },
  { value: 'D', label: '日期型' },
  { value: 'T', label: '时间型' },
];

/** 数据级别（r3 截图：1–4 级敏感度）。 */
export const DATA_LEVEL_OPTIONS: SelectOption[] = [
  { value: '1', label: '1 级' },
  { value: '2', label: '2 级' },
  { value: '3', label: '3 级' },
  { value: '4', label: '4 级' },
];

/** 数据分级（r13 代理服务：一般 / 重要 / 核心）。 */
export const DATA_GRADE_OPTIONS: SelectOption[] = [
  { value: 'general', label: '一般' },
  { value: 'important', label: '重要' },
  { value: 'core', label: '核心' },
];

/** 授权方式（r13 代理服务）。 */
export const AUTH_MODE_OPTIONS: SelectOption[] = [
  { value: 'provider', label: '提供方授权' },
  { value: 'platform', label: '平台授权' },
];

/** 文件存储类型（typed_resource_detail._FILE_STORE_LABELS 同口径）。 */
export const FILE_STORE_OPTIONS: SelectOption[] = [
  { value: 'centerStore', label: '中心库存储' },
  { value: 'localStore', label: '本地存储' },
  { value: 'objectStore', label: '对象存储' },
];

// ──────────────────────────────────────────────────────────────────────────
// 基本信息字段字典（在线编制第 1 步 16 字段 + 必填位）
//
// 必填口径单源 = 《问题反馈-0611 业务口径确认单》§A，负责人薛娇 2026-06-12 确认
// （草案建议列全采纳，含 #6 内部部门=选填、#16 数据资源摘要=必填）。
// 一处定义、三处生效：表单红星标注（P5InlineCatalogWizard）、提交前预检
// （missingRequiredBasicFields）、后端提交校验（catalog.entry.submit_review）。
// 后端镜像 = zw_brain/command/handlers/j1/catalog_entry.py `_INLINE_BASIC_REQUIRED_FIELDS`
// （无现成生成物同步机制，两表改动必须同步；以本字典为口径权威）。
// ──────────────────────────────────────────────────────────────────────────

export type BasicFieldRequiredRule =
  | 'required' // 必填：红星 + 提交前校验
  | 'optional' // 选填
  | 'auto' // 系统自动生成 / 自动带出，无需人填
  | 'requiredIfConditionalShare'; // 共享类型 = 有条件共享 时必填，其余选填

/** 「有条件共享」的共享类型码（SHARE_TYPE_OPTIONS value）。 */
export const CONDITIONAL_SHARE_TYPE = '2';

export interface BasicInfoFieldSpec {
  /** summary_json 键；title 例外（落 record 顶层 name/title 列）。 */
  key: string;
  label: string;
  rule: BasicFieldRequiredRule;
}

/** 在线编制「基本信息维护」16 字段（与旧平台同名页面字段对齐）。 */
export const BASIC_INFO_FIELDS: BasicInfoFieldSpec[] = [
  { key: 'title', label: '数据资源目录名称', rule: 'required' },
  { key: 'data_catalog_code', label: '数据资源目录代码', rule: 'auto' },
  { key: 'provider', label: '数据资源提供方', rule: 'auto' },
  { key: 'catalog_type', label: '数据资源分类', rule: 'required' },
  { key: 'source_system', label: '来源系统', rule: 'required' },
  { key: 'internal_org_name', label: '内部部门', rule: 'optional' },
  { key: 'domain', label: '所属领域', rule: 'required' },
  { key: 'application_scenario', label: '应用场景', rule: 'required' },
  { key: 'resource_format', label: '信息资源格式', rule: 'required' },
  { key: 'business_update_cycle', label: '业务更新周期', rule: 'required' },
  { key: 'data_update_cycle', label: '数据更新周期', rule: 'required' },
  { key: 'shared_way', label: '共享方式', rule: 'required' },
  { key: 'shared_type', label: '共享类型', rule: 'required' },
  { key: 'open_type', label: '开放类型', rule: 'required' },
  { key: 'shared_condition', label: '共享条件', rule: 'requiredIfConditionalShare' },
  { key: 'description', label: '数据资源摘要', rule: 'required' },
];

/** 表单标注用：该字段当前是否必填（共享条件随共享类型联动）。 */
export function basicFieldRequired(key: string, sharedType?: string): boolean {
  const spec = BASIC_INFO_FIELDS.find((f) => f.key === key);
  if (!spec) return false;
  if (spec.rule === 'required') return true;
  if (spec.rule === 'requiredIfConditionalShare') return (sharedType ?? '') === CONDITIONAL_SHARE_TYPE;
  return false;
}

/** 提交前预检：返回缺失必填项的中文名列表（与后端提交校验同一口径）。 */
export function missingRequiredBasicFields(values: Record<string, unknown>): string[] {
  const sharedType = String(values.shared_type ?? '');
  const missing: string[] = [];
  for (const spec of BASIC_INFO_FIELDS) {
    if (spec.rule === 'auto' || spec.rule === 'optional') continue;
    if (spec.rule === 'requiredIfConditionalShare' && sharedType !== CONDITIONAL_SHARE_TYPE) continue;
    const value = values[spec.key];
    if (value === null || value === undefined || String(value).trim() === '') missing.push(spec.label);
  }
  return missing;
}

/** 单条信息项（catalog item，写入 payload.items[]）。 */
export interface CatalogItemDraft {
  title: string;
  englishName: string;
  itemType: string;
  itemLength: string;
  shareType: string;
  shareCondition: string;
  dataLevel: string;
  /** 是否必填（旧平台 data_resource_table_column.is_null_field「是否为空」反向语义）。 */
  isRequired: boolean;
  note: string;
}

export function blankCatalogItem(): CatalogItemDraft {
  return {
    title: '',
    englishName: '',
    itemType: 'C',
    itemLength: '',
    shareType: '2',
    shareCondition: '',
    dataLevel: '3',
    isRequired: false,
    note: '',
  };
}

/** 信息项草稿 → payload.items[] 行（后端 repo.upsert_item 入库 summary_json）。
 * item_code 由 catalog_code + index 派生（编制期无独立编码，发布激活时归一）。
 */
export function catalogItemToPayload(item: CatalogItemDraft, catalogCode: string, index: number): Record<string, unknown> {
  return {
    item_code: `${catalogCode}#item-${index + 1}`,
    title: item.title.trim(),
    item_kind: 'field',
    display_order: index + 1,
    summary_json: {
      english_name: item.englishName.trim() || null,
      item_type: item.itemType || null,
      item_length: item.itemLength.trim() || null,
      shared_type: item.shareType || null,
      shared_condition: item.shareCondition.trim() || null,
      data_level: item.dataLevel || null,
      // is_null_field 旧平台语义为「是否允许为空」——必填 = 不允许为空 = '0'，可空 = '1'。
      is_null_field: item.isRequired ? '0' : '1',
      is_required: item.isRequired,
      note: item.note.trim() || null,
    },
  };
}
