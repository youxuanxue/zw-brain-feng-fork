// B1.1 网关运行只读面板封装：调用后端 ops.service.report.query（status=live /
// journey=b1），只取 gateways[] 渲染网关在线/降级/离线运行状态。与 useAuditPanels
// 同 pattern（postSkill + PanelSource pill + 失败回退 fixture）。
//
// 设计边界（read model，对应 .feature S9 / preflight 段 25 adapter-write-ban）：
//   - 只读。本 composable 不暴露任何写路径；网关路由 / 认证 / 限流策略仍回到
//     resource_channel_binding.gateway_policy_json 或外部网关策略系统。
//   - 承接旧 /openapi/report 网关心跳的 B1.1 读面（plan §3.3 / §3.5）。
import { ref, type Ref } from 'vue';
import { newRequestId, postSkill } from './useApiClient';
import type { PanelSource } from './useAuditPanels';
import { GATEWAY_RUNTIME_FIXTURE, type GatewayRuntimeResult } from '@/fixtures/b11-fixture';

export interface UseGatewayRuntimeResult {
  data: Ref<GatewayRuntimeResult | null>;
  source: Ref<PanelSource>;
  error: Ref<string | null>;
  load: (role?: string) => Promise<void>;
}

export function useGatewayRuntime(): UseGatewayRuntimeResult {
  const data = ref<GatewayRuntimeResult | null>(null);
  const source = ref<PanelSource>('idle');
  const error = ref<string | null>(null);

  async function load(role = 'ROLE_BUSIAUDIT'): Promise<void> {
    source.value = 'loading';
    error.value = null;
    try {
      const payload = await postSkill<{ gateways?: GatewayRuntimeResult['gateways'] }>(
        'ops.service.report.query',
        {
          role,
          tenant_id: 'sd-default',
          request_id: newRequestId('UI-GW'),
        },
      );
      if (!payload || !Array.isArray(payload.gateways)) throw new Error('payload shape unexpected');
      data.value = { gateways: payload.gateways };
      source.value = 'live';
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
      data.value = GATEWAY_RUNTIME_FIXTURE;
      source.value = 'fixture';
    }
  }

  return { data, source, error, load };
}
