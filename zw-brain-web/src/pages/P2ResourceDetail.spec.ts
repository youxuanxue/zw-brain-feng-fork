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
  w.findAll('button').find((b) => b.text() === '发起申请');
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

// R12 防回归（xj-review R-001）：消费视角（/discovery）必须隐藏含 DBA 物理字段的
// 「库表信息」块；供数管理视角（/provider）保留。守卫消费侧 物理表名 等实现细节不回潮泄漏
// ——此前该收口仅靠组件内 `sec.title === '库表信息'` 字符串耦合、无测试兜底，串名漂移会静默失守。
describe('P2ResourceDetail 库表信息（DBA 字段）消费视角隐藏', () => {
  // 暴露 title 的 DetailPanel 桩：默认桩 <div/> 吞掉 title，无法断言；这里把收到的
  // section title 写进 data-title，使「消费侧不应渲染 库表信息」可被真实断言（非空洞）。
  const titleStubs = {
    PageFocusHeader: { template: '<div/>' },
    DetailActions: { template: '<div><slot/></div>' },
    DetailPanel: { props: ['title', 'rows'], template: '<div class="dp" :data-title="title"></div>' },
  };
  const tableResource = {
    name: '历年GDP信息',
    id: 'res-1',
    status: '已发布',
    lifecycleStatus: 'active',
    typedDetail: {
      kind: 'table',
      kindLabel: '库表',
      sections: [{ title: '库表信息', rows: [{ label: '物理表名', value: 'lngdpxx' }] }],
    },
  };
  const sectionTitles = (w: ReturnType<typeof mount>) =>
    w.findAll('.dp').map((d) => d.attributes('data-title'));

  beforeEach(() => {
    resourceRef.value = null;
    loadingRef.value = false;
    fetchErrorRef.value = null;
    setProductRole('ROLE_ORGAN_OPERATER');
  });

  it('消费视角（/discovery）隐藏「库表信息」DBA 块', () => {
    routeState.path = '/discovery/resource/res-1';
    resourceRef.value = { ...tableResource };
    const w = mount(P2ResourceDetail, { global: { stubs: titleStubs } });
    expect(sectionTitles(w)).not.toContain('库表信息');
    expect(w.html()).not.toContain('物理表名');
  });

  it('供数管理视角（/provider）保留「库表信息」DBA 块', () => {
    routeState.path = '/provider/resource/res-1';
    resourceRef.value = { ...tableResource };
    const w = mount(P2ResourceDetail, { global: { stubs: titleStubs } });
    expect(sectionTitles(w)).toContain('库表信息');
  });
});
