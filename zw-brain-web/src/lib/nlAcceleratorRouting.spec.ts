import { describe, it, expect, vi, beforeEach } from 'vitest';

// Bug3 回归：找数助手「解析未命中」根因 = P2 NL 加速器对无权限岗位（search.intent.parse
// 返 403）把错误统统冒泡成 parse_status:'pending'（前端文案「解析未命中」）。
// 403 → 优雅降级到纯关键词搜索（搜索本身不依赖意图增强）+「当前岗位无找数助手增强」提示。
// 5xx/超时/网络中断 → 向上抛出，由面板渲染诚实错误态 + 重试（不再伪装「已直接搜索」）。

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

  it('非 403 失败（网络 / 5xx）→ 向上抛出，由面板渲染诚实错误态', async () => {
    postSkillMock.mockRejectedValueOnce(
      Object.assign(new Error('HTTP 500'), { status: 500 }),
    );
    await expect(
      parseNLAcceleratorLive('P2', '社保缴费', 'ROLE_ORGAN_OPERATER'),
    ).rejects.toMatchObject({ status: 500 });
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

  it('P3 输入资源式 32 位编号时，不生成申请详情跳转', async () => {
    postSkillMock.mockResolvedValueOnce({
      items: [{ id: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', status: 'pending', resourceName: '人口库' }],
    });
    const res = await parseNLAcceleratorLive(
      'P3',
      '查看 17ca754343fe4882bb099d12edf58b94 审批',
      'ROLE_ORGAN_MANAGER',
    );

    expect(res.parse_status).toBe('partial');
    expect(res.summary).toContain('不是资源编号');
    expect(res.actions).not.toContainEqual(
      expect.objectContaining({
        kind: 'navigate',
        target: '#/request-flow/request/17ca754343fe4882bb099d12edf58b94',
      }),
    );
    expect(postSkillMock).toHaveBeenCalledTimes(1);
  });

  it('B1.1 审计助手输入非申请 32 位编号时，只给审计回放，不跳申请详情', async () => {
    postSkillMock.mockResolvedValueOnce({
      items: [{ id: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', status: 'pending', resourceName: '人口库' }],
    });
    const res = await parseNLAcceleratorLive(
      'B1.1',
      '回放 17ca754343fe4882bb099d12edf58b94',
      'ROLE_BUSIAUDIT',
    );

    expect(res.parse_status).toBe('partial');
    expect(res.actions).toHaveLength(1);
    expect(res.actions[0]).toMatchObject({
      kind: 'invoke',
      target: 'audit.replay_evidence_chain',
      payload: { request_id: '17ca754343fe4882bb099d12edf58b94' },
    });
    expect(res.actions).not.toContainEqual(
      expect.objectContaining({
        kind: 'navigate',
        target: '#/request-flow/request/17ca754343fe4882bb099d12edf58b94',
      }),
    );
  });
});
