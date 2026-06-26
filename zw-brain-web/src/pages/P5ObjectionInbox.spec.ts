import { describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { setProductRole } from '@/composables/useProductRole';

const routeState = vi.hoisted(() => ({
  query: {} as Record<string, string>,
}));
const snapshotState = vi.hoisted(() => ({
  provider: { __v_isRef: true, value: {} as Record<string, unknown> },
  source: { __v_isRef: true, value: 'live' },
}));

vi.mock('vue-router', () => ({
  useRoute: () => routeState,
}));
vi.mock('@/composables/useSnapshot', () => ({
  useProvider: () => snapshotState.provider,
  useSnapshot: () => ({ source: snapshotState.source }),
}));
vi.mock('@/lib/objectionActions', () => ({
  acceptObjectionCase: vi.fn(),
}));

import P5ObjectionInbox from './P5ObjectionInbox.vue';

const stubs = {
  PageFocusHeader: {
    props: ['title', 'meta'],
    template: '<header><h1>{{ title }}</h1><p>{{ meta }}</p></header>',
  },
};

function mountPage() {
  return mount(P5ObjectionInbox, { global: { stubs } });
}

describe('P5ObjectionInbox pending scope', () => {
  it('uses provider.pending_objection_cases for workbench pending deep links', () => {
    setProductRole('ROLE_BUSIAUDIT');
    routeState.query = { scope: 'pending' };
    snapshotState.provider.value = {
      objection_cases: [
        { id: 'OBJ-PENDING', title: '测试目录描述不对', status: 'submitted' },
        { id: 'OBJ-INVESTIGATING', title: '核查中异议', status: 'platform_investigating' },
      ],
      pending_objection_cases: [
        { id: 'OBJ-PENDING', title: '测试目录描述不对', status: 'submitted' },
      ],
    };

    const wrapper = mountPage();

    expect(wrapper.get('h1').text()).toBe('待受理异议');
    expect(wrapper.findAll('[data-testid="objection-inbox-row"]')).toHaveLength(1);
    expect(wrapper.text()).toContain('测试目录描述不对');
    expect(wrapper.text()).not.toContain('核查中异议');
  });

  it('keeps the default inbox as all in-progress objections', () => {
    setProductRole('ROLE_BUSIAUDIT');
    routeState.query = {};
    snapshotState.provider.value = {
      objection_cases: [
        { id: 'OBJ-PENDING', title: '测试目录描述不对', status: 'submitted' },
        { id: 'OBJ-INVESTIGATING', title: '核查中异议', status: 'platform_investigating' },
      ],
      pending_objection_cases: [
        { id: 'OBJ-PENDING', title: '测试目录描述不对', status: 'submitted' },
      ],
    };

    const wrapper = mountPage();

    expect(wrapper.get('h1').text()).toBe('异议响应收件箱');
    expect(wrapper.findAll('[data-testid="objection-inbox-row"]')).toHaveLength(2);
    expect(wrapper.text()).toContain('测试目录描述不对');
    expect(wrapper.text()).toContain('核查中异议');
  });
});
