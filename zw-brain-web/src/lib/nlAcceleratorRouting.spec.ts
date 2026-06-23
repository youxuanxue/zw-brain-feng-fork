import { describe, it, expect, vi, beforeEach } from 'vitest';

// Bug3 回归：找数助手「解析未命中」根因 = P2 NL 加速器对无权限岗位（search.intent.parse
// 返 403）/ 任意调用失败，把错误统统冒泡成 parse_status:'pending'（前端文案「解析未命中」）。
// 修复后 parseP2 try/catch 优雅降级到纯关键词搜索动作（搜索本身不依赖意图增强），
// 403 额外给「当前岗位无找数助手增强」诚实提示。本 spec 通过 mock postSkill 锁定该行为。

const postSkillMock = vi.fn();
vi.mock('@/composables/useApiClient', () => ({
  postSkill: (...args: unknown[]) => postSkillMock(...args),
  newRequestId: (prefix: string) => `${prefix}-test`,
}));

import { parseNLAcceleratorLive } from './nlAcceleratorRouting';

describe('NL 加速器 P2 — 智能解析失败优雅降级（Bug3）', () => {
  beforeEach(() => {
    postSkillMock.mockReset();
  });

  it('403（无权限岗位）→ 不报「解析未命中」，回落关键词搜索 + 诚实提示', async () => {
    postSkillMock.mockRejectedValueOnce(
      Object.assign(new Error('HTTP 403 from search.intent.parse'), { status: 403 }),
    );
    const res = await parseNLAcceleratorLive('P2', '历年GDP信息', 'ROLE_SECURITY_AUDIT');
    // 仍可执行：给得出一个关键词搜索动作（绝不 pending 空态）。
    expect(res.parse_status).toBe('partial');
    expect(res.actions).toHaveLength(1);
    expect(res.actions[0]).toMatchObject({
      kind: 'filter',
      target: 'query',
      payload: { query: '历年GDP信息' },
    });
    // 403 专属诚实提示：区分「无权限」与「真没解析出动作」。
    expect(res.summary).toContain('当前岗位无');
  });

  it('403 + 命中专区词 → 回落到专区搜索动作', async () => {
    postSkillMock.mockRejectedValueOnce(
      Object.assign(new Error('HTTP 403'), { status: 403 }),
    );
    const res = await parseNLAcceleratorLive('P2', '我想找营商环境相关数据', 'ROLE_PLATFORM_OPERATER');
    expect(res.parse_status).toBe('partial');
    expect(res.actions[0]).toMatchObject({ kind: 'filter', target: 'zone' });
    expect(res.actions[0].payload).toMatchObject({ zone: '营商环境专区' });
  });

  it('非 403 失败（网络 / 5xx）→ 同样降级关键词搜索，提示不同', async () => {
    postSkillMock.mockRejectedValueOnce(
      Object.assign(new Error('HTTP 500'), { status: 500 }),
    );
    const res = await parseNLAcceleratorLive('P2', '社保缴费', 'ROLE_ORGAN_OPERATER');
    expect(res.parse_status).toBe('partial');
    expect(res.actions[0]).toMatchObject({ kind: 'filter', target: 'query', payload: { query: '社保缴费' } });
    expect(res.summary).toContain('智能解析暂不可用');
    expect(res.summary).not.toContain('当前岗位无');
  });

  it('降级时空查询 → 无可执行动作才落 pending（诚实空态）', async () => {
    postSkillMock.mockRejectedValueOnce(Object.assign(new Error('HTTP 403'), { status: 403 }));
    const res = await parseNLAcceleratorLive('P2', '   ', 'ROLE_SYSTEM');
    expect(res.actions).toHaveLength(0);
    expect(res.parse_status).toBe('pending');
  });

  it('成功路径（有权限岗位）保持原语义：意图增强产出搜索动作', async () => {
    postSkillMock.mockResolvedValueOnce({
      intent: 'search',
      keywords: ['GDP'],
      missing_fields: [],
      recommendation_reason: '已为你按 GDP 检索',
    });
    const res = await parseNLAcceleratorLive('P2', '历年GDP信息', 'ROLE_ORGAN_OPERATER');
    expect(res.parse_status).toBe('ok');
    expect(res.actions[0]).toMatchObject({ kind: 'filter', target: 'query', payload: { query: 'GDP' } });
  });
});
