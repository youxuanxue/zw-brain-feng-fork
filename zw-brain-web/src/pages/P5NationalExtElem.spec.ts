import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { ref } from 'vue';
import { setProductRole } from '@/composables/useProductRole';

const sourceRef = ref('live');
const webuiRef = ref<Record<string, unknown>>({
  nationalChannel: {
    enabled: true,
    provisioned: false,
    syncReady: false,
    notice: '国家通道待配置接入信息',
    operatorSummary: '草拟与审核可用，发布同步需平台运维员补齐接入信息',
  },
});

const authFetchSpy = vi.fn();
const invokeSpy = vi.fn();

vi.mock('@/composables/useSnapshot', () => ({
  useSnapshot: () => ({ source: sourceRef }),
  useWebUiConfig: () => webuiRef,
}));
vi.mock('@/composables/useAuth', () => ({
  authFetch: (...args: unknown[]) => authFetchSpy(...args),
}));
vi.mock('@/composables/useActionStub', () => ({
  invokeActionStub: (...args: unknown[]) => invokeSpy(...args),
}));
vi.mock('@/composables/useApiBase', () => ({
  apiUrl: (path: string) => path,
}));

import P5NationalExtElem from './P5NationalExtElem.vue';

const stubs = {
  PageFocusHeader: { props: ['title', 'meta'], template: '<header><h1>{{ title }}</h1><p>{{ meta }}</p></header>' },
};

function mountPage() {
  return mount(P5NationalExtElem, { global: { stubs } });
}

describe('P5NationalExtElem 新建编制草稿', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-06-24T10:11:12Z'));
    sourceRef.value = 'live';
    webuiRef.value = {
      nationalChannel: {
        enabled: true,
        provisioned: false,
        syncReady: false,
        notice: '国家通道待配置接入信息',
        operatorSummary: '草拟与审核可用，发布同步需平台运维员补齐接入信息',
        opsRoute: '#/integration-admin',
        missingConfigItems: [{ label: '国家平台访问地址' }],
        missingExternalReadinessItems: [{ label: '国家平台真实回执与对账口径' }],
      },
    };
    setProductRole('ROLE_BUSIAUDIT');
    authFetchSpy.mockReset();
    authFetchSpy.mockResolvedValue({
      ok: true,
      json: async () => ({ items: [] }),
    });
    invokeSpy.mockReset();
    invokeSpy.mockResolvedValue({ ok: true, status: 200 });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('空输入直接点击也会创建可追踪草稿', async () => {
    const w = mountPage();
    await flushPromises();

    await w.get('[data-testid="nat-ext-create-btn"]').trigger('click');
    await flushPromises();

    expect(invokeSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        skillId: 'catalog.national_ext_elem.compile',
        payload: {
          action: 'create',
          task_code: 'C_NAT_20260624101112000',
          title: '国家扩展要素编制草稿',
        },
        successTitle: '已创建编制草稿',
      }),
    );
  });

  it('手填编号和名称时保留用户输入', async () => {
    const w = mountPage();
    await flushPromises();

    await w.get('[data-testid="nat-ext-new-code"]').setValue(' C_NAT_CUSTOM ');
    await w.get('[data-testid="nat-ext-new-title"]').setValue('国家事项扩展字段');
    await w.get('[data-testid="nat-ext-create-btn"]').trigger('click');
    await flushPromises();

    expect(invokeSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        payload: {
          action: 'create',
          task_code: 'C_NAT_CUSTOM',
          title: '国家事项扩展字段',
        },
      }),
    );
  });

  it('主管审核通过后进入待同步，接入凭据齐但上线资料未确认时不放行发布同步', async () => {
    webuiRef.value = {
      nationalChannel: {
        enabled: true,
        provisioned: true,
        syncReady: false,
        notice: '国家通道待确认上线资料',
        operatorSummary: '接入信息已配齐，发布同步仍需确认上线资料',
      },
    };
    authFetchSpy.mockResolvedValue({
      ok: true,
      json: async () => ({
        items: [
          {
            task_code: 'C_NAT_PENDING_SYNC',
            title: '待发布目录',
            compile_status: 'pending_national_sync',
          },
        ],
      }),
    });

    const w = mountPage();
    await flushPromises();

    expect(w.get('[data-testid="nat-ext-publish-btn"]').attributes('disabled')).toBeDefined();
    expect(w.text()).toContain('接入信息已配齐，发布同步仍需确认上线资料');
  });

  it('未就绪时展示缺项和运维配置入口，行内同步显示可见阻塞原因', async () => {
    authFetchSpy.mockResolvedValue({
      ok: true,
      json: async () => ({
        items: [
          {
            task_code: 'C_NAT_PENDING_SYNC',
            title: '待同步目录',
            compile_status: 'pending_national_sync',
          },
        ],
      }),
    });

    const w = mountPage();
    await flushPromises();

    const missing = w.get('[data-testid="nat-ext-readiness-missing"]');
    expect(missing.text()).toContain('国家平台访问地址');
    expect(missing.text()).toContain('国家平台真实回执与对账口径');
    expect(w.get('[data-testid="nat-ext-ops-link"]').attributes('href')).toBe('#/integration-admin');
    expect(w.get('[data-testid="nat-ext-sync-blocked-note"]').text()).toBe('待运维配置');
  });

  it('国家通道就绪后同步按钮调用 sync 动作', async () => {
    webuiRef.value = {
      nationalChannel: {
        enabled: true,
        provisioned: true,
        syncReady: true,
        notice: '国家通道已满足发布同步条件',
        operatorSummary: '国家通道已满足发布同步条件',
      },
    };
    authFetchSpy.mockResolvedValue({
      ok: true,
      json: async () => ({
        items: [
          {
            task_code: 'C_NAT_READY_SYNC',
            title: '待同步目录',
            compile_status: 'pending_national_sync',
          },
        ],
      }),
    });

    const w = mountPage();
    await flushPromises();

    await w.get('[data-testid="nat-ext-publish-btn"]').trigger('click');
    await flushPromises();

    expect(invokeSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        payload: {
          action: 'sync',
          task_code: 'C_NAT_READY_SYNC',
        },
        successTitle: '已同步国家平台',
      }),
    );
  });
});
