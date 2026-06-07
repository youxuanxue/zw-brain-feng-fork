/** P5 提供方向导 / 收件箱 → skill 契约字段映射。 */

import { mapReverseDraftCatalog } from '@/lib/reverseDraftPayload';

export function catalogCodeFromItem(raw: Record<string, unknown>): string {
  return String(raw.catalog_code ?? raw.legacy_object_ref ?? raw.id ?? '');
}

export function mapProviderCatalog(raw: Record<string, unknown>) {
  return mapReverseDraftCatalog(raw);
}

// 0605 批次 3（代理服务注册重写）：原 resourceCodeForApiService 已退役——它把演示 service id
// （svc-ledger-prefill/backflow）硬映射到 resource_code，是「API 服务化向导」演示壳的残留。
// 向导重写为「代理服务注册向导」后用户直接注册产出真实 resource_code，不再需要此映射；
// 同步删除即清掉对已退役 seed 演示服务的最后引用（承演示诚实化收口）。

export function buildQualityRuleUpsertPayload(catalog: ReturnType<typeof mapReverseDraftCatalog>) {
  const code = catalog.catalog_code || catalog.id;
  return {
    rule_code: `qr-${code.replace(/[^\w-]/g, '_')}`,
    rule_name: `${catalog.name} 完整性规则`,
    rule_kind: 'completeness',
    target_catalog_codes: [code],
  };
}
