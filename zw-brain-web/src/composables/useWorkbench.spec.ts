import { describe, expect, it, vi } from 'vitest';
import { defineComponent, nextTick } from 'vue';
import { mount } from '@vue/test-utils';

const authState = vi.hoisted(() => ({
  fetch: vi.fn(),
  session: { __v_isRef: true, value: { subject: 'dev' } },
}));

vi.mock('./useAuth', () => ({
  authFetch: authState.fetch,
  getSession: () => authState.session,
  hasAllowedProductRoles: () => true,
}));

vi.mock('./useProductRole', () => ({
  getProductRole: () => ({ __v_isRef: true, value: 'ROLE_BUSIAUDIT' }),
}));

vi.mock('./useApiBase', () => ({
  apiUrl: (path: string) => path,
}));

import { prefetchWorkbench, useWorkbench } from './useWorkbench';

const VIEW = {
  greeting: '本地调试',
  todos: [],
  aiSummary: { summary: 'ok', basis: [] },
};

function okResponse(payload = VIEW) {
  return {
    ok: true,
    json: vi.fn().mockResolvedValue(payload),
  };
}

describe('useWorkbench cache', () => {
  it('uses freshly prefetched workbench data on remount without a duplicate request', async () => {
    authState.fetch.mockResolvedValue(okResponse());

    await prefetchWorkbench('ROLE_BUSIAUDIT');
    expect(authState.fetch).toHaveBeenCalledTimes(1);

    const Probe = defineComponent({
      setup() {
        return useWorkbench('ROLE_BUSIAUDIT');
      },
      template: '<div />',
    });

    mount(Probe);
    await nextTick();
    await Promise.resolve();

    expect(authState.fetch).toHaveBeenCalledTimes(1);
  });
});
