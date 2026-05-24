import { ref } from 'vue';
import { authFetch } from './useAuth';
import { getFixtureFor, type NLAcceleratorParseResult } from '@/fixtures/nl-accelerator-fixture';

// F7 NL 加速器入口：把自然语言一句话经 /api/skills/nl.accelerator.parse 网关送到 brain，
// 返回结构化 action[]。后端未 land（E1/E3/E4 范围）走 fixture 兜底。
//
// §5.4.6 六问自检（架构基线 §5.4.4 + §5.4.5）：
//  Q1 替代主页面？N — panel 折叠态主页面零变化；展开后 panel 在右侧占 380px。
//  Q2 黑盒 chat？N — 输出永远是 StructuredAction[]；UI 端用按钮 / chip 渲染。
//  Q3 失败回落？Y — 后端 404/501/超时 → fixture 兜底 + 'NL 后端等 E* land' 提示。
//  Q4 用户 opt out？Y — 默认折叠 + 顶部 icon 一键收起。
//  Q5 输入隐私？经 registry gateway（/api/skills/...）走审计链（audit_required=true），
//                不会绕过 BFF 直接打外部 LLM。
//  Q6 减摩量？4 anchor 高频场景 vs 鼠标层级减约 50-70% 点击。

export type ParseSource = 'live' | 'fixture' | 'pending';

export { type StructuredAction, type NLAcceleratorParseResult } from '@/fixtures/nl-accelerator-fixture';

export function useNLAccelerator(pageAnchor: string) {
  const result = ref<NLAcceleratorParseResult | null>(null);
  const source = ref<ParseSource>('pending');
  const loading = ref(false);
  const error = ref<string | null>(null);

  async function parse(query: string, role = 'ROLE_ORGAN_OPERATER'): Promise<void> {
    loading.value = true;
    error.value = null;
    try {
      const resp = await authFetch('/api/skills/nl.accelerator.parse', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ role, input: query, page_anchor: pageAnchor }),
      });
      if (resp.ok) {
        const data = (await resp.json()) as NLAcceleratorParseResult;
        if (data && Array.isArray(data.actions)) {
          result.value = data;
          source.value = 'live';
          return;
        }
        throw new Error('payload shape unexpected');
      }
      throw new Error(`HTTP ${resp.status}`);
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
      const fixture = getFixtureFor(pageAnchor, query);
      if (fixture) {
        result.value = fixture;
        source.value = 'fixture';
      } else {
        result.value = {
          summary: `当前 NL 后端（nl.accelerator.parse）等 E1/E3/E4 land；可继续使用页面按钮直接操作。`,
          parse_status: 'pending',
          actions: [],
        };
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
