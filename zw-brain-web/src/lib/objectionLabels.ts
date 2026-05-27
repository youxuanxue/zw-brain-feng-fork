/** 异议（objection）类型映射 — Inbox / Detail / New 三页共用 R12 中文。 */

export const OBJECTION_TYPE_ZH: Record<string, string> = {
  catalog: '目录',
  resource: '资源',
  authorization: '授权',
  content: '内容',
  use: '使用',
  alert: '告警事件',
  delivery: '交付任务',
};

export function formatObjectionType(raw: string): string {
  return OBJECTION_TYPE_ZH[raw] ?? raw ?? '—';
}

/** 仅 resource/delivery 有 per-id 详情路由；catalog 只有浏览页（无 :id 详情）、其余类型返 undefined，UI 渲染纯文本。 */
export function objectionTargetHref(targetType: string, targetId: string): string | undefined {
  if (!targetId) return undefined;
  if (targetType === 'resource') return `#/discovery/resource/${targetId}`;
  if (targetType === 'delivery') return `#/delivery-exchange/task/${targetId}`;
  return undefined;
}
