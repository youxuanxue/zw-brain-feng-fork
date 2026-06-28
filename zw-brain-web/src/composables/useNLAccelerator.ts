import { ref } from 'vue';
import { getFixtureFor, type NLAcceleratorParseResult } from '@/fixtures/nl-accelerator-fixture';
import { getProductRole } from './useProductRole';
import { parseNLAcceleratorLive } from '@/lib/nlAcceleratorRouting';
import { fixtureFallbackAllowed } from '@/lib/panelFallback';

// F7 NL 加速器：page-anchor → E1 live skill 映射为主路径；fixture 仅最终兜底。
//
// §5.4.6 六问自检（架构基线 §5.4.4 + §5.4.5）：
//  Q1 替代主页面？N — panel 折叠态主页面零变化；展开后 panel 在右侧占 380px。
//  Q2 黑盒 chat？N — 输出永远是 StructuredAction[]；UI 端用按钮 / chip 渲染。
//  Q3 失败回落？Y — live skill 失败 → fixture 兜底（仅开发构建）→ pending 提示。
//      生产构建绝不上 fixture 假数据（承 D11 / panelFallback R-007），直接走 pending 诚实空态。
//  Q4 用户 opt out？Y — 默认折叠 + 顶部 icon 一键收起。
//  Q5 输入隐私？经 registry gateway（/api/skills/...）走审计链（audit_required=true），
//                不会绕过 BFF 直接打外部 LLM。
//  Q6 减摩量？4 anchor 高频场景 vs 鼠标层级减约 50-70% 点击。

export type ParseSource = 'live' | 'fixture' | 'pending';

export { type StructuredAction, type NLAcceleratorParseResult } from '@/fixtures/nl-accelerator-fixture';

const LIVE_ANCHORS = new Set(['P2', 'P3']);

export function useNLAccelerator(pageAnchor: string) {
  const result = ref<NLAcceleratorParseResult | null>(null);
  const source = ref<ParseSource>('pending');
  const loading = ref(false);
  const error = ref<string | null>(null);

  async function parse(query: string, role?: string): Promise<void> {
    loading.value = true;
    error.value = null;
    const effectiveRole = role ?? getProductRole().value;
    try {
      if (LIVE_ANCHORS.has(pageAnchor)) {
        const live = await parseNLAcceleratorLive(pageAnchor, query, effectiveRole);
        if (live && Array.isArray(live.actions)) {
          result.value = live;
          source.value = 'live';
          return;
        }
        throw new Error('live payload shape unexpected');
      }
      throw new Error(`no live routing for ${pageAnchor}`);
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
      // fixture 仅开发构建兜底（本地后端未起时走查）；生产构建一律不上假数据，
      // 直接落 pending 诚实空态（承 D11 业务数据禁 Mock / panelFallback R-007）。
      const fixture = fixtureFallbackAllowed() ? getFixtureFor(pageAnchor, query) : null;
      if (fixture) {
        result.value = fixture;
        source.value = 'fixture';
      } else {
        // 真后端调用失败（5xx / 超时 / 网络中断）且无 fixture 兜底：清空 result，让面板落到
        // 诚实的错误态（红色 + 重试入口），不再伪装成「解析未命中」的空成功结果。注意这只
        // 覆盖「调用抛错」一支；解析成功但零动作的合法空态走 try 分支、仍是正常非错误结果。
        result.value = null;
        source.value = 'pending';
      }
    } finally {
      loading.value = false;
    }
  }

  function clear(): void {
    result.value = null;
    source.value = 'pending';
    error.value = null;
  }

  return { result, source, loading, error, parse, clear };
}
