/** 异议（objection）类型映射 — Inbox / Detail / New 三页共用 R12 中文。 */

export const OBJECTION_TYPE_ZH: Record<string, string> = {
  catalog: '目录',
  resource: '资源',
  authorization: '授权',
  content: '内容',
  use: '使用',
  alert: '告警事件',
  delivery: '交付任务',
  // objection_kind 落库口径（legacy mapper 1→catalog_quality / 2→resource_quality；P3ObjectionNew
  // 的 objectionKind）——收件箱/详情按 kind 渲染时同样映射中文，避免 snake_case 标识符直出（R12）。
  catalog_quality: '目录质量',
  resource_quality: '资源质量',
  usage: '使用问题',
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
