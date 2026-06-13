import { ref, type Ref } from 'vue';
import { newRequestId, postSkill } from './useApiClient';
import { applyPanelFallback } from '@/lib/panelFallback';
import { SUMMARY_FIXTURE, type InvestigationSummaryResult } from '@/fixtures/b11-fixture';

// 调查摘要助手封装：调 assistant.investigation_summary（PR #91 58d5587 已 land
// main）。输入 panel kind + panel_payload；后端走 shared/inference/client，
// 脱敏后再送推理。UI 上助手摘要与原始 panel 数据**并列展示**，不替代原始证据
// （架构 D14 不覆盖原始审计证据约束）。共享 BFF 客户端见 useApiClient.ts。

// 'error' = 生产构建下 API 失败的诚实不可用态（R-007）。
export type AssistantSource = 'idle' | 'loading' | 'live' | 'fixture' | 'error';

export interface UseSummaryResult {
  data: Ref<InvestigationSummaryResult | null>;
  source: Ref<AssistantSource>;
  error: Ref<string | null>;
  load: (
    panel: 'statistics' | 'anomaly' | 'accountability',
    panelPayload: Record<string, unknown>,
    role?: string
  ) => Promise<void>;
  reset: () => void;
}

export function useInvestigationSummary(): UseSummaryResult {
  const data = ref<InvestigationSummaryResult | null>(null);
  const source = ref<AssistantSource>('idle');
  const error = ref<string | null>(null);

  async function load(
    panel: 'statistics' | 'anomaly' | 'accountability',
    panelPayload: Record<string, unknown>,
    role = 'ROLE_SECURITY_AUDIT'
  ): Promise<void> {
    source.value = 'loading';
    error.value = null;
    try {
      const payload = await postSkill<InvestigationSummaryResult>('assistant.investigation_summary', {
        role,
        panel,
        panel_payload: panelPayload,
        tenant_id: 'sd-default',
        request_id: newRequestId('UI-INV'),
        max_tokens: 800,
      });
      if (!payload || typeof payload.summary !== 'string') throw new Error('payload shape unexpected');
      data.value = payload;
      source.value = payload.model === 'rule-fallback' ? 'fixture' : 'live';
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
      applyPanelFallback({ data, source }, SUMMARY_FIXTURE, null);
    }
  }

  function reset(): void {
    data.value = null;
    source.value = 'idle';
    error.value = null;
  }

  return { data, source, error, load, reset };
}
