import { describe, it, expect, beforeEach, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { ref } from 'vue';
import { setProductRole } from '@/composables/useProductRole';

// 受控 resource，绕开网络/auth 挂载副作用，只验「未发布资源诚实兜底文案 + 申请按钮状态门」。
const resourceRef = ref<Record<string, unknown> | null>(null);
const loadingRef = ref(false);
const fetchErrorRef = ref<string | null>(null);
vi.mock('@/composables/useResourceDetail', () => ({
  useResourceDetail: () => ({ resource: resourceRef, loading: loadingRef, fetchError: fetchErrorRef }),
}));
vi.mock('@/composables/useResourceSchema', () => ({
  useResourceSchema: () => ({ columns: ref([]), loading: ref(false), fetchError: ref(null), isEmpty: ref(true) }),
}));
const invokeSpy = vi.fn();
vi.mock('@/composables/useActionStub', () => ({
  invokeActionStub: (...args: unknown[]) => invokeSpy(...args),
}));
vi.mock('@/composables/useRequestNavigation', () => ({
  navigateToRequestDetail: vi.fn(),
  resolveRequestIdFromAction: vi.fn(),
}));
// route.path 可控（D62 档 B：/provider/resource/:id 走供数管理视角，按 route.path 判，非 route.query）。
const routeState = vi.hoisted(() => ({ path: '/discovery/resource/res-1' }));
vi.mock('vue-router', () => ({ useRoute: () => ({ params: { id: 'res-1' }, path: routeState.path, query: {} }) }));

import P2ResourceDetail from './P2ResourceDetail.vue';

const stubs = {
  PageFocusHeader: { template: '<div/>' },
  DetailPanel: { template: '<div/>' },
  DetailActions: { template: '<div><slot/></div>' },
};
const mountPage = () => mount(P2ResourceDetail, { global: { stubs } });
const applyBtn = (w: ReturnType<typeof mountPage>) =>
  w.findAll('button').find((b) => b.text() === '申请资源');
const notPublishedNote = (w: ReturnType<typeof mountPage>) =>
  w.find('[data-testid="resource-not-published-note"]');
const providerManageNote = (w: ReturnType<typeof mountPage>) =>
  w.find('[data-testid="resource-provider-manage-note"]');

describe('P2ResourceDetail 未发布资源诚实兜底', () => {
  beforeEach(() => {
    resourceRef.value = null;
    loadingRef.value = false;
    fetchErrorRef.value = null;
    routeState.path = '/discovery/resource/res-1';
    setProductRole('ROLE_ORGAN_OPERATER');
    invokeSpy.mockReset();
  });

  it('已发布（active）+ 有申请权限：渲染申请按钮，不出诚实说明', () => {
    resourceRef.value = { name: 'X', lifecycleStatus: 'active' };
    const w = mountPage();
    expect(applyBtn(w)).toBeTruthy();
    expect(notPublishedNote(w).exists()).toBe(false);
  });

  it('待发布（approved_pending_publish）+ 有申请权限：不出申请按钮，渲染诚实说明（消除断头路）', () => {
    resourceRef.value = { name: 'X', lifecycleStatus: 'approved_pending_publish' };
    const w = mountPage();
    expect(applyBtn(w)).toBeFalsy();
    const note = notPublishedNote(w);
    expect(note.exists()).toBe(true);
    expect(note.text()).toContain('尚未发布');
  });

  it('已暂停（suspended）+ 有申请权限：不出申请按钮，渲染诚实说明', () => {
    resourceRef.value = { name: 'X', lifecycleStatus: 'suspended' };
    const w = mountPage();
    expect(applyBtn(w)).toBeFalsy();
    expect(notPublishedNote(w).exists()).toBe(true);
  });

  it('无申请权限岗位（安全审计员）+ 未发布：申请按钮与诚实说明均不渲染（无权=不可见，不需解释）', () => {
    setProductRole('ROLE_SECURITY_AUDIT');
    resourceRef.value = { name: 'X', lifecycleStatus: 'approved_pending_publish' };
    const w = mountPage();
    expect(applyBtn(w)).toBeFalsy();
    expect(notPublishedNote(w).exists()).toBe(false);
  });

  it('资源未加载（null）：不出诚实说明（避免空态误报）', () => {
    resourceRef.value = null;
    const w = mountPage();
    expect(notPublishedNote(w).exists()).toBe(false);
  });

  // D62 档 B：供数侧详情走独立路由 /provider/resource/:id —— 供数方来管理自己的数据、非来申请。
  it('/provider 路由 + 未发布：抑制「暂不可申请」与申请按钮，改出供数管理视角回链（消除心智错配）', () => {
    routeState.path = '/provider/resource/res-1';
    resourceRef.value = { name: 'X', lifecycleStatus: 'approved_pending_publish' };
    const w = mountPage();
    expect(applyBtn(w)).toBeFalsy();
    expect(notPublishedNote(w).exists()).toBe(false);
    const note = providerManageNote(w);
    expect(note.exists()).toBe(true);
    expect(note.text()).toContain('回供数管理');
  });

  it('/provider 路由 + 已发布（active）：供数方不显「申请」按钮，出管理视角回链（不申请自己的数据）', () => {
    routeState.path = '/provider/resource/res-1';
    resourceRef.value = { name: 'X', lifecycleStatus: 'active' };
    const w = mountPage();
    expect(applyBtn(w)).toBeFalsy();
    expect(providerManageNote(w).exists()).toBe(true);
  });
});
