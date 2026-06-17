import { describe, it, expect, beforeEach, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { ref } from 'vue';
import type { WorkbenchView, WorkbenchTodo } from '@/fixtures/workbench-fixture';
import { setProductRole } from '@/composables/useProductRole';

// 把 useWorkbench 整体替换成可控 stub，避开 auth/网络挂载副作用，只验 P1 的行渲染分支。
const viewRef = ref<WorkbenchView | null>(null);
vi.mock('@/composables/useWorkbench', () => ({
  useWorkbench: () => ({
    data: viewRef,
    source: ref('live'),
    error: ref(null),
    refresh: vi.fn(),
  }),
}));

import P1Workbench from './P1Workbench.vue';

const actionableTodo: WorkbenchTodo = {
  id: 'REQ-X-1',
  title: '人口基础信息复用申请待部门审核',
  status: '待部门审核',
  href: '#/request-flow/request/REQ-X-1',
  action: {
    kind: 'decision',
    capability: 'application.dept_approve',
    gate: 'application.dept_approve',
    basePayload: { request_id: 'REQ-X-1' },
    context: [{ label: '资源', value: '人口基础信息共享目录' }],
    decisions: [
      { label: '审核通过', tone: 'primary', success: '已授权', payload: { decision: 'approve' } },
    ],
  },
};
const plainTodo: WorkbenchTodo = {
  id: 'REQ-X-2',
  title: '专项摸排任务退回补充',
  status: '待修改',
  href: '#/request-flow/request/REQ-X-2',
};
// 聚合待办：两条「待发布资源」，gate=resource.asset.publish（仅业务运营员有权）。
const listTodo: WorkbenchTodo = {
  id: 'WB-PUBLISH',
  title: '待发布资源 2 条',
  status: '待发布',
  action: {
    kind: 'decision-list',
    items: [
      {
        id: 'res-A',
        label: '市场主体登记基础信息',
        capability: 'resource.asset.publish',
        gate: 'resource.asset.publish',
        basePayload: { resource_code: 'res-A' },
        context: [],
        decisions: [
          { label: '发布', tone: 'primary', success: '已发布', payload: { decision: 'publish' } },
        ],
      },
      {
        id: 'res-B',
        label: '不动产登记结果信息',
        capability: 'resource.asset.publish',
        gate: 'resource.asset.publish',
        basePayload: { resource_code: 'res-B' },
        context: [],
        decisions: [
          { label: '发布', tone: 'primary', success: '已发布', payload: { decision: 'publish' } },
        ],
      },
    ],
  },
};

function makeView(todos: WorkbenchTodo[]): WorkbenchView {
  return {
    greeting: '您好',
    subtitle: '',
    todos,
    aiSummary: { summary: '建议先跟进。', basis: [] },
  };
}

function mountPage() {
  return mount(P1Workbench, {
    global: {
      // 行内面单独有自己的单测意图不在此重复；这里只验 P1 是否挂出面（toggle + panel）。
      stubs: { WorkbenchTodoActionPanel: { template: '<div class="stub-panel" />' } },
    },
  });
}

describe('P1Workbench 行内办理', () => {
  beforeEach(() => {
    viewRef.value = null;
  });

  it('带 action 且有权（部门管理员）→ 渲染展开办理切换 + 展开后挂出决策面', async () => {
    setProductRole('ROLE_ORGAN_MANAGER');
    viewRef.value = makeView([actionableTodo]);
    const w = mountPage();
    await w.vm.$nextTick();

    const toggle = w.find('[data-testid="workbench-todo-expand"]');
    expect(toggle.exists()).toBe(true);
    // 默认收起：标题是文本而非深链，面未挂出。
    expect(w.find('[data-testid="workbench-todo-link"]').exists()).toBe(false);
    expect(w.find('[data-testid="workbench-todo-action-panel"]').exists()).toBe(false);
    expect(w.find('.stub-panel').exists()).toBe(false);

    await toggle.trigger('click');
    expect(w.find('.stub-panel').exists()).toBe(true);
    expect(toggle.text()).toContain('收起');

    await toggle.trigger('click');
    expect(w.find('.stub-panel').exists()).toBe(false);
    expect(toggle.text()).toContain('展开办理');
  });

  it('带 action 但无权（安全审计员）→ 回落原深链，无展开切换', async () => {
    setProductRole('ROLE_SECURITY_AUDIT');
    viewRef.value = makeView([actionableTodo]);
    const w = mountPage();
    await w.vm.$nextTick();

    expect(w.find('[data-testid="workbench-todo-expand"]').exists()).toBe(false);
    const link = w.find('[data-testid="workbench-todo-link"]');
    expect(link.exists()).toBe(true);
    expect(link.attributes('href')).toBe('#/request-flow/request/REQ-X-1');
  });

  it('无 action 的待办 → 照旧渲染深链', async () => {
    setProductRole('ROLE_ORGAN_MANAGER');
    viewRef.value = makeView([plainTodo]);
    const w = mountPage();
    await w.vm.$nextTick();

    expect(w.find('[data-testid="workbench-todo-expand"]').exists()).toBe(false);
    expect(w.find('[data-testid="workbench-todo-link"]').exists()).toBe(true);
  });

  it('decision-list 且至少一条记录有权（业务运营员）→ 可展开办理', async () => {
    setProductRole('ROLE_BUSIAUDIT');
    viewRef.value = makeView([listTodo]);
    const w = mountPage();
    await w.vm.$nextTick();

    const toggle = w.find('[data-testid="workbench-todo-expand"]');
    expect(toggle.exists()).toBe(true);
    expect(w.find('.stub-panel').exists()).toBe(false);
    await toggle.trigger('click');
    expect(w.find('.stub-panel').exists()).toBe(true);
  });

  it('decision-list 但无一条记录有权（安全审计员）→ 无展开切换、回落纯文本', async () => {
    setProductRole('ROLE_SECURITY_AUDIT');
    viewRef.value = makeView([listTodo]);
    const w = mountPage();
    await w.vm.$nextTick();

    expect(w.find('[data-testid="workbench-todo-expand"]').exists()).toBe(false);
    // 无 href → 标题渲染为纯文本，既无展开亦无深链。
    expect(w.find('[data-testid="workbench-todo-link"]').exists()).toBe(false);
    expect(w.text()).toContain('待发布资源 2 条');
  });
});
