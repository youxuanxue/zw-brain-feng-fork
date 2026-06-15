/** P5 提供方向导 / 收件箱 → skill 契约字段映射。 */

import { mapReverseDraftCatalog } from '@/lib/reverseDraftPayload';

export function catalogCodeFromItem(raw: Record<string, unknown>): string {
  return String(raw.catalog_code ?? raw.legacy_object_ref ?? raw.id ?? '');
}

/** 新铸一个本地系统生成的资源/目录标识（j2-<prefix>-<时间戳36>-<随机4>）。
 *  原本散落在 P5ApiServiceWizard / P5InlineCatalogWizard 各写一份同形 `_newXxxCode()`，
 *  抽到此处单源——挂接向导也复用，资源码不再让用户手敲（手敲易与目录归属脱钩、被
 *  后端跨 org 校验拒）。技术 id / 路由键，不是国家登记码，不伪造业务码语义。 */
export function mintResourceCode(prefix: string): string {
  const ts = Date.now().toString(36);
  const rnd = Math.random().toString(36).slice(2, 6);
  return `j2-${prefix}-${ts}-${rnd}`;
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
