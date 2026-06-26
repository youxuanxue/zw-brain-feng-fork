import { describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';

const routeState = vi.hoisted(() => ({ path: '/login' }));
const authState = vi.hoisted(() => ({
  user: { __v_isRef: true, value: null },
  session: { __v_isRef: true, value: null },
  loading: { __v_isRef: true, value: false },
}));
const snapshotState = vi.hoisted(() => ({
  source: { __v_isRef: true, value: 'live' },
  data: { __v_isRef: true, value: null },
  webui: { __v_isRef: true, value: {} },
}));

vi.mock('vue-router', () => ({
  RouterLink: {
    props: ['to'],
    template: '<a class="router-link" :href="typeof to === \'string\' ? to : \'#\'"><slot /></a>',
  },
  RouterView: { template: '<div data-testid="router-view" />' },
  useRoute: () => routeState,
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), currentRoute: { value: routeState } }),
}));

vi.mock('@/composables/useAuth', () => ({
  bootstrap: vi.fn().mockResolvedValue(undefined),
  getCurrentUser: () => authState.user,
  getSession: () => authState.session,
  getAllowedProductRoles: () => [],
  hasAllowedProductRoles: () => false,
  hasPendingOAuthCallback: () => false,
  isAuthLoading: () => authState.loading,
  logout: vi.fn(),
  PRODUCT_ROLE_LABELS: {
    ROLE_ORGAN_OPERATER: '部门操作员',
  },
}));

vi.mock('@/composables/useSnapshot', () => ({
  loadSnapshot: vi.fn().mockResolvedValue(undefined),
  prefetchSnapshot: vi.fn(),
  useSnapshot: () => snapshotState,
  useWebUiConfig: () => snapshotState.webui,
}));

vi.mock('@/composables/useWorkbench', () => ({
  prefetchWorkbench: vi.fn(),
}));

vi.mock('@/composables/useActionStub', () => ({
  pushToast: vi.fn(),
}));

import App from './App.vue';

describe('App shell brand', () => {
  it('renders the product mark asset in the header', () => {
    const wrapper = mount(App, {
      global: {
        stubs: {
          ActionToast: true,
          PlatformGuideChatPanel: true,
          ProductSideNav: true,
        },
      },
    });

    const logo = wrapper.get('img.gov-logo-mark');
    expect(logo.attributes('src')).toContain('zw-brain-mark.svg');
    expect(logo.attributes('alt')).toBe('');
    expect(wrapper.find('.global-brand .brand-title').text()).toBe('政务数据大脑');
  });
});
