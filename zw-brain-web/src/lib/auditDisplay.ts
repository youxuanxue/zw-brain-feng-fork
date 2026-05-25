/** B1 合规/接入页：审计与数据源字段的用户可见文案（R12，禁止英文枚举直出）。 */

export function formatDataSource(src: string): string {
  const map: Record<string, string> = {
    live: '实时数据',
    fixture: '演示数据',
    loading: '加载中',
    idle: '',
    error: '不可用',
  };
  return map[src] ?? '';
}

export function formatSeverity(severity: string): string {
  const map: Record<string, string> = {
    high: '高',
    medium: '中',
    low: '低',
  };
  return map[severity] ?? severity;
}

export function formatDeniedChainCount(total: number): string {
  if (total <= 0) return '该对象近期无拒绝访问记录。';
  return `共 ${total} 条拒绝访问链路。`;
}

export function formatActorLabel(actor: string): string {
  const raw = String(actor ?? '').trim();
  if (!raw) return '—';
  const parts = raw.split(':');
  const name = parts[parts.length - 1];
  if (name && /[\u4e00-\u9fff]/.test(name)) return name;
  return raw;
}
