/** P5 提供方向导 / 收件箱 → skill 契约字段映射。 */

import { mapReverseDraftCatalog } from '@/lib/reverseDraftPayload';

export function catalogCodeFromItem(raw: Record<string, unknown>): string {
  return String(raw.catalog_code ?? raw.legacy_object_ref ?? raw.id ?? '');
}

export function mapProviderCatalog(raw: Record<string, unknown>) {
  return mapReverseDraftCatalog(raw);
}

/** API 服务化向导：service id → resource_code（seed 演示映射 + 资源列表兜底）。 */
export function resourceCodeForApiService(
  serviceId: string,
  provider: Record<string, unknown>,
): string {
  const known: Record<string, string> = {
    'svc-ledger-prefill': 'res-jbxx-ledger',
    'svc-ledger-backflow': 'res-jbxx-ledger',
  };
  if (known[serviceId]) return known[serviceId];
  const resources = Array.isArray(provider.resources) ? provider.resources : [];
  for (const row of resources) {
    const it = row as Record<string, unknown>;
    const id = String(it.id ?? '');
    const type = String(it.type ?? '');
    if (type.includes('API') || type.includes('库表') || id.startsWith('res-')) {
      return id;
    }
  }
  return 'res-jbxx-ledger';
}

export function buildQualityRuleUpsertPayload(catalog: ReturnType<typeof mapReverseDraftCatalog>) {
  const code = catalog.catalog_code || catalog.id;
  return {
    rule_code: `qr-${code.replace(/[^\w-]/g, '_')}`,
    rule_name: `${catalog.name} 完整性规则`,
    rule_kind: 'completeness',
    target_catalog_codes: [code],
  };
}
