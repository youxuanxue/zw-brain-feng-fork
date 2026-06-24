import { beforeEach, describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { computed, ref } from 'vue';
import { setProductRole } from '@/composables/useProductRole';

const webuiRef = ref<Record<string, unknown>>({});
const loadSnapshotSpy = vi.fn();
const packageLoadSpy = vi.fn();

vi.mock('@/composables/useSnapshot', () => ({
  useWebUiConfig: () => computed(() => webuiRef.value),
  loadSnapshot: (...args: unknown[]) => loadSnapshotSpy(...args),
}));

vi.mock('@/composables/usePackageLifecycle', () => ({
  usePackageList: () => ({
    source: ref('live'),
    data: ref({ items: [] }),
    error: ref(null),
    load: packageLoadSpy,
  }),
  disableTenantCapability: vi.fn(),
  enableTenantCapability: vi.fn(),
  reviewPackage: vi.fn(),
  updatePackageTrustLevel: vi.fn(),
}));

vi.mock('@/composables/useActionStub', () => ({ pushToast: vi.fn() }));
vi.mock('@/lib/consumeNLAction', () => ({ consumeNLAction: vi.fn() }));

import B12IntegrationAdmin from './B12IntegrationAdmin.vue';

const stubs = {
  PageFocusHeader: { template: '<header><slot/><slot name="aside"/></header>' },
  DataSourceBadge: { template: '<span />' },
  NLAcceleratorPanel: { template: '<aside />' },
};

function mountPage() {
  return mount(B12IntegrationAdmin, { global: { stubs } });
}

describe('B12IntegrationAdmin 国家通道运行态', () => {
  beforeEach(() => {
    setProductRole('ROLE_SYSTEM');
    loadSnapshotSpy.mockReset();
    loadSnapshotSpy.mockResolvedValue(null);
    packageLoadSpy.mockReset();
    packageLoadSpy.mockResolvedValue(undefined);
    webuiRef.value = {
      nationalChannel: {
        enabled: true,
        provisioned: false,
        syncReady: false,
        operatorSummary: '草拟与审核可用，发布同步需平台运维员补齐接入信息',
        configItems: [
          { label: '启用国家通道', ready: true },
          { label: '国家平台访问地址', ready: false },
        ],
        externalReadinessItems: [
          { label: '国家下发基本要素目录与模板数据', ready: false },
        ],
        missingConfigItems: [{ label: '国家平台访问地址', ready: false }],
        missingExternalReadinessItems: [{ label: '国家下发基本要素目录与模板数据', ready: false }],
        opsChecklist: [
          {
            key: 'env_config',
            label: '补齐接入配置',
            detail: '由平台运维员在部署环境注入国家平台地址、请求方身份、接入账号、接入密钥和接口服务标识映射。',
            blocked: true,
          },
        ],
      },
    };
  });

  it('平台运维页展示国家通道配置状态和缺失外部资料', () => {
    const w = mountPage();
    const card = w.get('[data-testid="national-channel-ops-card"]');

    expect(card.text()).toContain('国家通道');
    expect(card.text()).toContain('待补齐');
    expect(card.text()).toContain('草拟与审核可用，发布同步需平台运维员补齐接入信息');
    expect(card.text()).toContain('已配启用国家通道');
    expect(card.text()).toContain('待补国家平台访问地址');
    expect(card.text()).toContain('待确认国家下发基本要素目录与模板数据');
    expect(card.text()).toContain('配置生效步骤');
    expect(card.text()).toContain('补齐接入配置');
    expect(card.text()).toContain('当前阻塞项');
    expect(card.text()).toContain('配置来源');
    expect(card.text()).toContain('接入配置');
    expect(card.text()).toContain('上线资料确认');
    expect(card.text()).toContain('国家平台访问地址');
    expect(card.text()).not.toContain('ZW_BRAIN_');
  });

  it('接入凭据齐但上线资料未确认时仍显示待补齐', () => {
    webuiRef.value = {
      nationalChannel: {
        enabled: true,
        provisioned: true,
        syncReady: false,
        operatorSummary: '接入信息已配齐，发布同步仍需确认上线资料',
        configItems: [{ label: '接入密钥', ready: true }],
        externalReadinessItems: [{ label: '国家平台真实回执与对账口径', ready: false }],
      },
    };

    const w = mountPage();
    const card = w.get('[data-testid="national-channel-ops-card"]');

    expect(card.text()).toContain('待补齐');
    expect(card.text()).toContain('接入信息已配齐，发布同步仍需确认上线资料');
    expect(card.text()).toContain('待确认国家平台真实回执与对账口径');
  });
});
