/**
 * 用户语言层（R12 渲染兜底单一事实源）。
 *
 * 政务客户读到的每一个字都该是业务人话。后端数据通道里会混入工程标识——
 * 能力 id（如 ledger.entity.base.read）、渠道 token（exchange）、意图名
 * （discover_resource）、裸 ISO 时间戳、无名记录的 32 位 hex id。这些一旦
 * 直出就是「产品对客户说工程师的语言」。
 *
 * 本层是渲染前的最后一道兜底：所有面向用户的标题 / 描述 / 渠道 / 时间，
 * 经此处降级为业务用语再交给模板。既有零散 label 映射（statusLabels /
 * auditDisplay / packageDisplay）继续各管其状态枚举，本层只补它们没覆盖的
 * 「标识符泄漏」一类，不另起第二套状态字典。
 *
 * 设计纪律：
 *  - 未登记的标识符必须降级，绝不裸出（fail-closed 到通用业务名）。
 *  - 映射键是纯 ASCII token（命中段 24 黑名单的中文不进字符串字面值）。
 *  - 纯函数、无副作用，e2e 渲染守卫据此断言零命中。
 */

// ── 渠道 token → 业务用语 ────────────────────────────────────────────────
const CHANNEL_ZH: Record<string, string> = {
  exchange: '交换通道',
  recurring_exchange: '交换通道', // F2：周期交换也归「交换通道」，不落泛化「数据通道」。
  internal: '内部直达',
  external: '外部对接',
  national: '国家通道',
  share: '共享交付',
  api: '接口服务',
  service: '接口服务',
  file: '文件交付',
  folder: '文件交付',
  db: '库表交付',
  // F2（6.4#15）：legacy 交付渠道可能直接是 res_type（table 等），补齐映射避免落到泛化「数据通道」。
  table: '库表交付',
  // F2：审批通过新建在产单的 channel 是复合态「受控交付 + 审计回执」（request.py 落库），
  // 收敛为简洁的「受控交付」（核对语义已由库表「核对交换结果」操作承载，渠道列不重复啰嗦）。
  '受控交付 + 审计回执': '受控交付',
};

/** 交付 / 申请渠道 token → 中文；未登记的 ASCII slug 兜底为「数据通道」。 */
export function formatChannel(raw: unknown): string {
  const key = String(raw ?? '').trim();
  if (!key) return '—';
  if (CHANNEL_ZH[key]) return CHANNEL_ZH[key];
  if (/[一-鿿]/.test(key)) return key; // 已是中文，原样
  if (/^[a-z][a-z0-9_.-]*$/i.test(key)) return '数据通道';
  return key;
}

// 资源生命周期态 → 中文展示态：单一事实源在后端（zw_brain/domain/resource_lifecycle.py），
// 由 serializer/卡片随记录下发 status(中文)+lifecycleStatus(原值)，前端零词表、只读不译（R12）。
// 此处原 RESOURCE_STATUS_ZH / formatResourceStatus 镜像词表已退役，避免「两份词表手同步漂移」。

// ── 意图名 → 业务用语 ────────────────────────────────────────────────────
const INTENT_ZH: Record<string, string> = {
  discover_resource: '查找可申请数据',
  query_application: '查看我的申请进度',
  register_demand: '登记数据需求',
  unknown: '理解你的诉求',
};

/** NL 加速器意图 token → 中文业务动作；未登记兜底为「理解你的诉求」。 */
export function formatIntent(raw: unknown): string {
  const key = String(raw ?? '').trim();
  if (!key) return INTENT_ZH.unknown;
  if (INTENT_ZH[key]) return INTENT_ZH[key];
  if (/[一-鿿]/.test(key)) return key;
  return INTENT_ZH.unknown;
}

// ── 能力 / 待办标识符 → 业务用语 ──────────────────────────────────────────
// 仅登记真正会出现在用户待办 / 列表里的能力族前缀；命中前缀给出业务名，
// 未命中一律降级为通用「待办事项」。绝不把 a.b.c 形态的裸 id 直出。
const CAPABILITY_PREFIX_ZH: Array<[RegExp, string]> = [
  [/^request\./, '共享申请待办'],
  [/^catalog\./, '目录维护待办'],
  [/^topic\./, '专题包待办'],
  [/^delivery\./, '交付待办'],
  [/^credential\./, '凭据待办'],
  [/^objection\./, '异议处理待办'],
  [/^resource\./, '资源审核待办'],
  [/^ledger\./, '台账核对待办'],
  [/^audit\./, '审计核查待办'],
  [/^policy\./, '策略配置待办'],
  [/^package\./, '接入审核待办'],
  [/^national\./, '国家通道待办'],
];

const DOTTED_ID_RE = /^[a-z][a-z0-9]*(\.[a-z][a-z0-9_]*){2,}$/;
const SNAKE_ID_RE = /^[a-z][a-z0-9]*(_[a-z0-9]+)+$/;

/**
 * 把一条待办 / 列表标题降级为业务人话。
 *  - 标题里夹了能力 id（如 "ledger.entity.base.read 能力包待审核"）→ 即便含中文，
 *    也必须先把 id 段 + 内部词「能力包」替换成业务名，绝不让 id 直出。
 *  - 整条是裸能力 id（a.b.c）/ 裸 snake_case → 「待办事项」。
 *  - 纯中文真实标题 → 原样返回（真实业务名优先）。
 */
export function humanizeTitle(raw: unknown): string {
  const text = String(raw ?? '').trim();
  if (!text) return '待办事项';
  // 1) 标题里夹了能力 id（无论是否带中文）→ id 段映射业务名 + 去内部词「能力包」。
  const dotted = text.match(/[a-z][a-z0-9]*(?:\.[a-z][a-z0-9_]*){2,}/);
  if (dotted) {
    const id = dotted[0];
    const rest = text.replace(id, '').replace(/能力包|capability/gi, '').trim();
    for (const [re, label] of CAPABILITY_PREFIX_ZH) {
      if (re.test(id)) return rest ? `${label} · ${rest}` : label;
    }
    // 未登记前缀：保留剩余中文业务描述（若有），否则通用化。
    return rest && /[一-鿿]/.test(rest) ? rest : '待办事项';
  }
  // 2) 纯中文真实标题 → 原样返回（真实业务名优先）。
  if (/[一-鿿]/.test(text)) return text;
  // 3) 整条是裸标识符 → 通用化。
  if (DOTTED_ID_RE.test(text) || SNAKE_ID_RE.test(text)) return '待办事项';
  return text;
}

// ── 时间本地化 ───────────────────────────────────────────────────────────
/** ISO 8601 / 带微秒时间戳 → 本地 `YYYY-MM-DD HH:mm`；非时间原样。 */
export function formatTime(raw: unknown): string {
  const text = String(raw ?? '').trim();
  if (!text) return '—';
  // 已是 YYYY-MM-DD HH:mm（无 T / 无微秒）→ 原样
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/.test(text)) return text;
  // 仅日期
  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return text;
  const d = new Date(text);
  if (Number.isNaN(d.getTime())) {
    // 非合法时间但形似 ISO（含 T / 微秒）→ 至少剥到分钟，不裸出微秒
    const m = text.match(/^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})/);
    if (m) return `${m[1]} ${m[2]}`;
    return text;
  }
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(
    d.getMinutes(),
  )}`;
}

// ── 无名记录派生名 ───────────────────────────────────────────────────────
const HEX_32_RE = /^[0-9a-f]{32}$/i;
const HEX_24PLUS_RE = /^[0-9a-f]{24,}$/i;

/** 一段文本是否「就是」一个长 hex id（≥24 位纯 hex），即裸 id 当标题。 */
export function isBareHexId(raw: unknown): boolean {
  const text = String(raw ?? '').trim();
  return HEX_24PLUS_RE.test(text);
}

// 文本里夹了 ≥24 位 hex token（如 "<hex> 交付任务"）：本质仍是「id + 类别词」拼名，
// 不是真实业务名。
const HEX_TOKEN_RE = /\b[0-9a-f]{24,}\b/i;

/** 文本中是否含一个长 hex token（即便有中文后缀也算「无真实名」）。 */
export function containsBareHexId(raw: unknown): boolean {
  return HEX_TOKEN_RE.test(String(raw ?? ''));
}

// 长编号（≥24 位、无空格/中文的标识符：hex / 全数字目录码 / 大小写混编码）
// 作为次要 chip 时统一缩成末 6 位，full 值留在 :title 悬浮可见。
const LONG_CODE_RE = /^[0-9A-Za-z]{24,}$/;

/** id / 编号末 6 位短码（用于次要 chip 展示，避免整条长编号撑爆列）。 */
export function shortId(raw: unknown): string {
  const text = String(raw ?? '').trim();
  if (!text) return '—';
  if (HEX_32_RE.test(text) || HEX_24PLUS_RE.test(text) || LONG_CODE_RE.test(text))
    return `…${text.slice(-6)}`;
  // 复合长编号（前缀 + ≥24 位 hex token，如 DLV-<uuid4hex>：D56 新铸单的派生交付码）：
  // 整段渲染等于把裸 hex 当主文本（R12 hex-32 泄漏），同样缩末 6 位；full 值由调用方
  // :title / :href 保全（详情可达性不受影响）。
  if (HEX_TOKEN_RE.test(text)) return `…${text.slice(-6)}`;
  return text;
}

/**
 * 给一条记录派生用户可读名：优先真实名；名缺失 / 名本身就是裸 hex id →
 * 用类别词 + 末 6 位派生「<类别> …末6位」，绝不把 32 位 hex 当标题主文本。
 *
 * @param name 记录真实名（可能为空 / 为 hex）
 * @param id 记录 id（用于派生末 6 位）
 * @param category 业务类别词（如「交付任务」「申请单」「导入记录」）
 */
export function deriveRecordName(
  name: unknown,
  id: unknown,
  category = '导入记录',
): string {
  const n = String(name ?? '').trim();
  // 真实名：非空 且 不含长 hex token（"<hex> 交付任务" 这类拼名视为无真实名）。
  if (n && !containsBareHexId(n)) return n;
  const i = String(id ?? '').trim();
  if (i) return `${category} ${shortId(i)}`;
  // id 也缺：从拼名里至少剥掉 hex token，保留尾部类别词。
  const stripped = n.replace(HEX_TOKEN_RE, '').trim();
  return stripped || category;
}

// ── 错误文案诚实化 ───────────────────────────────────────────────────────
const HTTP_STATUS_RE = /\bHTTP\s+\d{3}\b/i;

/**
 * 把抛出/捕获的错误信息降级为用户人话：含 HTTP 状态码（HTTP 404）的技术
 * 错误 → 统一诚实提示，不把状态码当用户文案。其余短中文错误原样透传。
 */
export function humanizeError(raw: unknown, fallback = '暂时无法加载，请稍后再试。'): string {
  const text = String(raw ?? '').trim();
  if (!text) return fallback;
  if (HTTP_STATUS_RE.test(text)) return fallback;
  return text;
}

// ── 专题包描述降级 ───────────────────────────────────────────────────────
// 渲染层禁止 placeholder 直出：描述为空 / 含工程占位词（projection / 可见性
// projection / placeholder）→ 降级为由关联目录数派生的诚实描述。
const PLACEHOLDER_DESC_RE =
  /projection|placeholder|可见性\s*projection|共享目录可见性|占位|todo|tbd/i;

/**
 * 专题包卡片描述：真实业务描述优先；为空 / 是工程占位文案 → 用关联目录数
 * 派生一句诚实描述。绝不把 "共享目录可见性 projection" 这类占位直出。
 */
export function topicPackageDesc(rawDesc: unknown, catalogCount: number): string {
  const desc = String(rawDesc ?? '').trim();
  if (desc && !PLACEHOLDER_DESC_RE.test(desc)) return desc;
  if (catalogCount > 0) return `已归集 ${catalogCount} 个共享目录，可订阅使用。`;
  return '专题包正在归集共享目录。';
}
