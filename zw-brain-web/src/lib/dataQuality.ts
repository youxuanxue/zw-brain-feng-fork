/**
 * 数据质量分类器（前端镜像）— 真实导入单「用途」脏值的机械化判定。
 *
 * 权威规则源在后端 `zw_brain/domain/data_quality.py`；本文件是前端镜像，
 * 用于列表渲染时**降级脏值**（不裸奔）。两侧由 tests/test_data_quality_classifier.py
 * 的固定样例（测试 / 167 / 169,167 / 空）守住一致——改一侧规则须同改另一侧。
 *
 * 客户试用反馈（0604，业务方试用反馈 + 截图）：「用途列出现『测试』『167』这类脏值」。
 * 裁决：列表脏值降级显示「未填写用途」次要样式，不再把历史脏值伪装成供数据页待办。
 */

/** 列表降级文案（与后端 MISSING_PURPOSE_LABEL 一致）。 */
export const MISSING_PURPOSE_LABEL = '未填写用途';

export type PurposeQuality = 'clean' | 'empty' | 'numeric_only' | 'placeholder' | 'too_short';

// 占位/测试词枚举（去空白 + 转小写后精确匹配）。与后端 _PLACEHOLDER_TOKENS 一致。
const PLACEHOLDER_TOKENS: ReadonlySet<string> = new Set([
  '测试',
  'test',
  '测试数据',
  'demo',
  '演示',
  '无',
  '暂无',
  '待填',
  '待补充',
  'n/a',
  'na',
  'null',
  'none',
  '-',
  '—',
  '1',
  '0',
]);

// 纯数字 / 数字 + 常见分隔符（逗号 / 顿号 / 横线 / 斜杠 / 点 / 空格）。
const NUMERIC_ONLY = /^[\d\s,，、\-/.]+$/;

/** 返回脏值类目；clean = 合法用途（不降级），其余 = 脏值。 */
export function classifyPurpose(raw: string | null | undefined): PurposeQuality {
  const text = (raw ?? '').trim();
  if (!text) return 'empty';
  const lowered = text.toLowerCase();
  if (PLACEHOLDER_TOKENS.has(lowered)) return 'placeholder';
  if (NUMERIC_ONLY.test(text)) return 'numeric_only';
  if (text.replace(/\s+/g, '').length < 2) return 'too_short';
  return 'clean';
}

/** 脏值判定：非 clean → true（列表降级）。 */
export function isDirtyPurpose(raw: string | null | undefined): boolean {
  return classifyPurpose(raw) !== 'clean';
}

/**
 * 列表展示用途：脏值 → 降级文案（次要样式由调用方据 dirty 标志渲染）。
 * 返回 { text, dirty }：text 是该显示的字符串，dirty 决定是否打次要灰样式。
 */
export function displayPurpose(raw: string | null | undefined): { text: string; dirty: boolean } {
  if (isDirtyPurpose(raw)) return { text: MISSING_PURPOSE_LABEL, dirty: true };
  return { text: (raw ?? '').trim(), dirty: false };
}
