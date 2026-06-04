/**
 * R12 渲染层禁用模式 —— 单一事实源。
 *
 * 政务客户的截图实锤：动态数据（待办标题 / 渠道 / 时间 / hex id / 占位描述）
 * 走数据通道绕过了静态守卫段 24，把工程语言直出到了 UI。本模块把「什么文本
 * 不该出现在渲染后的可见 DOM 里」编码成可机械执行的正则单源，由
 * r12_rendered_language.spec.ts 遍历全部场景页断言零命中。
 *
 * 单源原则：正则只在此处定义；spec 与（未来可选的）静态守卫共用，不写两份。
 */

export interface ForbiddenPattern {
  /** 类别标识，命中报告里用。 */
  id: string;
  /** 人话说明，命中清单可读。 */
  label: string;
  /** 在一段可见文本里查找禁用片段；返回所有命中（去重在调用侧）。 */
  find: (text: string) => string[];
}

/** 裸 capability / intent token：a.b.c（≥3 段点分小写标识符）。 */
const DOTTED_TOKEN = /\b[a-z][a-z0-9]*(?:\.[a-z][a-z0-9_]*){2,}\b/g;

/** 裸 snake_case 标识符：foo_bar(_baz)*（小写下划线，无中文）。 */
const SNAKE_TOKEN = /\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b/g;

/** HTTP 状态码文案：HTTP 404 / HTTP 500 等。 */
const HTTP_STATUS = /\bHTTP\s+\d{3}\b/g;

/** 裸 ISO 8601 含 T 分隔 / 微秒的时间戳（如 2026-05-29T06:54:49.795706）。 */
const ISO_TIMESTAMP = /\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b/g;

/** ≥32 位裸 hex（作为主文本时即「裸 hex 当标题」）。 */
const HEX_32 = /\b[0-9a-f]{32,}\b/gi;

/**
 * snake_case 白名单：合法英文复合词 / 技术属性名，出现在可见文本里不算泄漏。
 * 每条豁免须可解释——这些是产品里允许出现的英文（不是后端枚举 slug 直出）。
 * 注意：白名单按「整段命中字符串相等」匹配，不做子串放行，避免被借道刷绿。
 */
export const SNAKE_WHITELIST = new Set<string>([
  // —— 目前无合法 snake_case 可见文本；保留空集合 + 显式说明，
  //    未来若产品确需展示英文复合词（如某协议字段名），在此逐条登记并注明理由。
]);

/** R12 黑名单中文词（对齐 scripts/check_ui_term_blacklist.py），出现在可见中文里即泄漏。 */
export const BLACKLIST_WORDS = [
  'projection',
  'capability',
  'package',
  'write-with-audit',
  'register-version',
  'apply-tenant-policy',
  'reconcile-receipt',
  'submit-evidence',
  'policy_decision',
] as const;

/**
 * 业务可见词白名单：含黑名单子串但本身是合法政务用语 / 中文短语的整词，
 * 不应被误判。例如「专题包」「凭据」等纯中文不含 ASCII 黑名单 token，
 * 天然不会命中（黑名单是 ASCII）。此处仅留扩展位。
 */
const BLACKLIST_LINE_ALLOW = /R12-allow/;

function blacklistFind(text: string): string[] {
  if (BLACKLIST_LINE_ALLOW.test(text)) return [];
  const hits: string[] = [];
  for (const w of BLACKLIST_WORDS) {
    // 黑名单词都是 ASCII；只在「这段可见文本含中文」时才视为 UI 泄漏
    // （纯 ASCII 文本可能是被意外渲染的 code chip，由 hex / token 规则另行覆盖）。
    const re = new RegExp(w.replace(/[-_]/g, '[-_]'), 'i');
    if (re.test(text) && /[一-鿿]/.test(text)) hits.push(w);
  }
  return hits;
}

export const FORBIDDEN_PATTERNS: ForbiddenPattern[] = [
  {
    id: 'dotted-token',
    label: '裸 capability/intent token（a.b.c）',
    find: (t) => Array.from(t.matchAll(DOTTED_TOKEN), (m) => m[0]),
  },
  {
    id: 'snake-token',
    label: 'snake_case 标识符直出',
    find: (t) =>
      Array.from(t.matchAll(SNAKE_TOKEN), (m) => m[0]).filter((s) => !SNAKE_WHITELIST.has(s)),
  },
  {
    id: 'http-status',
    label: 'HTTP 状态码当用户文案',
    find: (t) => Array.from(t.matchAll(HTTP_STATUS), (m) => m[0]),
  },
  {
    id: 'iso-timestamp',
    label: '裸 ISO 8601 时间戳（含 T / 微秒）',
    find: (t) => Array.from(t.matchAll(ISO_TIMESTAMP), (m) => m[0]),
  },
  {
    id: 'hex-32',
    label: '≥32 位裸 hex 作主文本',
    find: (t) => Array.from(t.matchAll(HEX_32), (m) => m[0]),
  },
  {
    id: 'blacklist-word',
    label: 'R12 黑名单工程词漏入中文文案',
    find: blacklistFind,
  },
];

/**
 * 对一段可见文本跑全部禁用模式，返回命中清单（{patternId, sample}）。
 * 调用侧（spec）按页聚合、去重、断言为零。
 */
export function scanForbidden(text: string): Array<{ patternId: string; label: string; sample: string }> {
  const out: Array<{ patternId: string; label: string; sample: string }> = [];
  const seen = new Set<string>();
  for (const p of FORBIDDEN_PATTERNS) {
    for (const sample of p.find(text)) {
      const key = `${p.id}::${sample}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({ patternId: p.id, label: p.label, sample });
    }
  }
  return out;
}
