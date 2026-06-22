/** 工作台 / 申请流状态：禁止把后端枚举 slug 直接展示给用户（R12）。 */
const REQUEST_STATUS_ZH: Record<string, string> = {
  pending: '审批中',
  supplementing: '补录中',
  'summary-pending': '待汇总确认',
  completed: '已汇总',
  'need-fix': '待补正',
  rejected: '已驳回',
  approved: '已通过',
  dept_approved: '已受理待审核',
  in_delivery: '交付中',
  granted: '已授权',
  revoked: '已撤销',
  expired: '已过期',
  suspended: '已暂停',
  draft: '草稿',
  reconciling: '待核对',
  issued: '已签发',
  not_issued: '未签发',
  // 交付任务
  planned: '已计划',
  published: '已发布',
  running: '运行中',
  stopped: '已停止',
  delivered: '已交付',
  active: '进行中',
  failed: '失败',
  // 异议 / 通用
  submitted: '已提交',
  platform_investigating: '平台核查中',
  provider_investigating: '部门核查中',
  resolved: '已解决',
  closed: '已关闭',
  escalated: '已升级',
  accepted: '已受理',
  // 供需 6 步
  gap_discovered: '发现缺口',
  registered: '已登记',
  recommend_failed: '推荐未命中',
  manual_registered: '人工登记',
  provider_responded: '部门已响应',
  subscribed: '已订阅',
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
  if (key === 'rejected' || key === '已驳回' || key === 'revoked' || key === '已撤销' || key === 'expired' || key === '已过期') return 'tone-danger';
  return 'tone-neutral';
}
