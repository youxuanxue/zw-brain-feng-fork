import { describe, it, expect, beforeEach, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import type {
  WorkbenchTodoActionList,
  WorkbenchTodoActionSingle,
} from '@/fixtures/workbench-fixture';

// invokeActionStub / pushToast 收口为 mock，避开网络与 toast 副作用，只验面内逻辑：
// 渲染逐条记录、理由门两态、下发载荷合并 reasonKey。
const invokeActionStub = vi.fn().mockResolvedValue({ ok: true, status: 200 });
const pushToast = vi.fn();
vi.mock('@/composables/useActionStub', () => ({
  invokeActionStub: (...args: unknown[]) => invokeActionStub(...args),
  pushToast: (...args: unknown[]) => pushToast(...args),
}));

import WorkbenchTodoActionPanel from './WorkbenchTodoActionPanel.vue';

// 业务运营员对 resource.asset.publish 有权（pageAccess SoT）→ 按钮可见。
const ROLE = 'ROLE_BUSIAUDIT';

const listAction: WorkbenchTodoActionList = {
  kind: 'decision-list',
  items: [
    {
      id: 'res-A',
      label: '市场主体登记基础信息（库表）',
      capability: 'resource.asset.publish',
      gate: 'resource.asset.publish',
      basePayload: { resource_code: 'res-A' },
      context: [{ label: '资源形态', value: '库表' }],
      decisions: [
        { label: '发布', tone: 'primary', success: '资源已发布', payload: { decision: 'publish' } },
        {
          label: '退回',
          tone: 'danger',
          success: '已退回',
          payload: { decision: 'return_for_fix' },
          needsReason: true,
          reasonKey: 'reject_reason',
        },
      ],
    },
    {
      id: 'res-B',
      label: '不动产登记结果信息（文件）',
      capability: 'resource.asset.publish',
      gate: 'resource.asset.publish',
      basePayload: { resource_code: 'res-B' },
      context: [{ label: '资源形态', value: '文件' }],
      decisions: [
        { label: '发布', tone: 'primary', success: '资源已发布', payload: { decision: 'publish' } },
      ],
    },
  ],
};

function mountList(role = ROLE) {
  return mount(WorkbenchTodoActionPanel, { props: { action: listAction, role } });
}

describe('WorkbenchTodoActionPanel · decision-list', () => {
  beforeEach(() => {
    invokeActionStub.mockClear();
    pushToast.mockClear();
  });

  it('渲染 N 条记录，每条带各自的决策按钮', () => {
    const w = mountList();
    const items = w.findAll('[data-testid="workbench-decision-item"]');
    expect(items.length).toBe(2);
    // 第一条两个决策、第二条一个 → 共 3 个决策按钮。
    expect(w.findAll('[data-testid="workbench-todo-decision"]').length).toBe(3);
    expect(w.text()).toContain('市场主体登记基础信息（库表）');
    expect(w.text()).toContain('不动产登记结果信息（文件）');
  });

  it('无理由的决策（发布）→ 立即下发，载荷合并 item.basePayload + decision.payload', async () => {
    const w = mountList();
    const firstPublish = w
      .findAll('[data-testid="workbench-todo-decision"]')
      .find((b) => b.text() === '发布');
    await firstPublish!.trigger('click');
    expect(invokeActionStub).toHaveBeenCalledTimes(1);
    expect(invokeActionStub).toHaveBeenCalledWith({
      skillId: 'resource.asset.publish',
      payload: { resource_code: 'res-A', decision: 'publish' },
      successTitle: '资源已发布',
    });
  });

  it('国家通道未配置时展示真实 pending 回执原因', async () => {
    invokeActionStub.mockResolvedValueOnce({
      ok: true,
      status: 200,
      data: {
        national_channel: {
          status: 'pending',
          reason: '国家通道待配置接入信息，已记录转报意图',
        },
      },
    });
    const nationalAction: WorkbenchTodoActionList = {
      kind: 'decision-list',
      items: [
        {
          id: 'A-NAT-1',
          label: '国家级数据申请',
          capability: 'application.escalate_national',
          gate: 'application.escalate_national',
          basePayload: { application_code: 'A-NAT-1' },
          context: [{ label: '申请资源', value: '国家级数据申请' }],
          decisions: [
            {
              label: '转报国家平台',
              tone: 'primary',
              success: '已提交国家通道',
              payload: { action: 'escalate' },
            },
          ],
        },
      ],
    };
    const w = mount(WorkbenchTodoActionPanel, {
      props: { action: nationalAction, role: 'ROLE_BUSIAUDIT' },
    });

    await w.get('[data-testid="workbench-todo-decision"]').trigger('click');

    expect(invokeActionStub).toHaveBeenCalledWith({
      skillId: 'application.escalate_national',
      payload: { application_code: 'A-NAT-1', action: 'escalate' },
      successTitle: '已提交国家通道',
    });
    expect(pushToast).toHaveBeenCalledWith({
      kind: 'warn',
      title: '国家通道待接入',
      detail: '国家通道待配置接入信息，已记录转报意图',
    });
  });

  it('needsReason 的决策（退回）→ 首点展开理由框，不立即下发', async () => {
    const w = mountList();
    expect(w.find('[data-testid="workbench-decision-reason"]').exists()).toBe(false);
    const reject = w
      .findAll('[data-testid="workbench-todo-decision"]')
      .find((b) => b.text() === '退回');
    await reject!.trigger('click');
    // 理由框出现，但尚未下发。
    expect(w.find('[data-testid="workbench-decision-reason"]').exists()).toBe(true);
    expect(invokeActionStub).not.toHaveBeenCalled();
  });

  it('填写理由后确认 → 按 reasonKey 合并理由进载荷下发', async () => {
    const w = mountList();
    const reject = w
      .findAll('[data-testid="workbench-todo-decision"]')
      .find((b) => b.text() === '退回');
    await reject!.trigger('click');
    const textarea = w.find('[data-testid="workbench-decision-reason"]');
    await textarea.setValue('字段缺失，请补全后重提');
    await w.find('[data-testid="workbench-decision-reason-confirm"]').trigger('click');
    expect(invokeActionStub).toHaveBeenCalledTimes(1);
    expect(invokeActionStub).toHaveBeenCalledWith({
      skillId: 'resource.asset.publish',
      payload: {
        resource_code: 'res-A',
        decision: 'return_for_fix',
        reject_reason: '字段缺失，请补全后重提',
      },
      successTitle: '已退回',
    });
  });

  it('理由为空确认 → 不下发、提示填写', async () => {
    const w = mountList();
    const reject = w
      .findAll('[data-testid="workbench-todo-decision"]')
      .find((b) => b.text() === '退回');
    await reject!.trigger('click');
    await w.find('[data-testid="workbench-decision-reason-confirm"]').trigger('click');
    expect(invokeActionStub).not.toHaveBeenCalled();
    expect(pushToast).toHaveBeenCalled();
  });

  it('无权岗位（安全审计员）→ GatedAction 自门控，按钮不渲染', () => {
    const w = mountList('ROLE_SECURITY_AUDIT');
    // 记录行仍在（聚合面已展开），但每个决策按钮被 GatedAction 挡掉。
    expect(w.findAll('[data-testid="workbench-decision-item"]').length).toBe(2);
    expect(w.findAll('[data-testid="workbench-todo-decision"]').length).toBe(0);
  });
});

// kind='decision'（M1 单条）分支保持不变：仍渲染要点面板 + 整组门控按钮。
const singleAction: WorkbenchTodoActionSingle = {
  kind: 'decision',
  capability: 'application.dept_approve',
  gate: 'application.dept_approve',
  basePayload: { request_id: 'REQ-1' },
  context: [{ label: '资源', value: '人口基础信息共享目录' }],
  decisions: [
    { label: '审核通过', tone: 'primary', success: '已授权', payload: { decision: 'approve' } },
  ],
};

describe('WorkbenchTodoActionPanel · decision（M1 不变）', () => {
  beforeEach(() => invokeActionStub.mockClear());

  it('有权岗位（部门管理员）→ 渲染要点面板 + 决策按钮，点击下发合并载荷', async () => {
    const w = mount(WorkbenchTodoActionPanel, {
      props: { action: singleAction, role: 'ROLE_ORGAN_MANAGER' },
    });
    expect(w.text()).toContain('办理要点');
    const btn = w.find('[data-testid="workbench-todo-decision"]');
    expect(btn.exists()).toBe(true);
    await btn.trigger('click');
    expect(invokeActionStub).toHaveBeenCalledWith({
      skillId: 'application.dept_approve',
      payload: { request_id: 'REQ-1', decision: 'approve' },
      successTitle: '已授权',
    });
  });
});
