/** 工作台 / 申请流状态：禁止把后端枚举 slug 直接展示给用户（R12）。 */
const REQUEST_STATUS_ZH: Record<string, string> = {
  pending: '审批中',
  supplementing: '补录中',
  'summary-pending': '待汇总确认',
  completed: '已汇总',
  'need-fix': '待补正',
  rejected: '已驳回',
  approved: '已通过',
  in_delivery: '交付中',
  granted: '已授权',
  revoked: '已撤销',
  draft: '草稿',
  reconciling: '待对账',
  issued: '已签发',
  not_issued: '未签发',
};

const SLUG_RE = /^[a-z][a-z0-9_-]*$/;

/** 将待办 status 转为中文；已是中文则原样返回。 */
export function formatTodoStatus(raw: string): string {
  const key = String(raw ?? '').trim();
  if (!key) return '—';
  if (REQUEST_STATUS_ZH[key]) return REQUEST_STATUS_ZH[key];
  if (SLUG_RE.test(key)) return '待处理';
  return key;
}

/** 状态徽标色调（用于列表右侧 pill）。 */
export function todoStatusTone(raw: string): string {
  const key = String(raw ?? '').trim();
  if (/待|补|改|审|核|告警|拦截|异常|处理中|预警/.test(key)) return 'tone-warn';
  if (key === 'approved' || key === '已通过' || key === '可查看' || key === 'granted' || key === '已授权' || key === 'issued' || key === '已签发')
    return 'tone-ok';
  if (key === 'in_delivery' || key === '交付中' || key === '补录中') return 'tone-info';
  if (key === 'rejected' || key === '已驳回') return 'tone-danger';
  return 'tone-neutral';
}
