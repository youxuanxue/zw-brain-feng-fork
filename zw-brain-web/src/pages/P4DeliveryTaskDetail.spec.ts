import { describe, it, expect, beforeEach, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { ref, computed } from 'vue';
import { setProductRole } from '@/composables/useProductRole';

// 受控 task + source，绕开网络/auth 挂载副作用，只验失败态恢复 CTA 的「状态门 + 无权=不可见」。
const taskRef = ref<Record<string, unknown> | null>(null);
const sourceRef = ref('live');
vi.mock('@/composables/useSnapshot', () => ({
  useSnapshot: () => ({ source: sourceRef }),
  lookupDeliveryTask: () => computed(() => taskRef.value),
}));
const invokeSpy = vi.fn();
vi.mock('@/composables/useActionStub', () => ({
  invokeActionStub: (...args: unknown[]) => invokeSpy(...args),
}));
vi.mock('@/composables/useDeliveryDownload', () => ({ downloadDeliveryFile: vi.fn() }));
vi.mock('vue-router', () => ({ useRoute: () => ({ params: { id: 'D-1' } }) }));

import P4DeliveryTaskDetail from './P4DeliveryTaskDetail.vue';

const stubs = {
  PageFocusHeader: { template: '<div/>' },
  DetailPanel: { template: '<div/>' },
  PhaseTrack: { template: '<div/>' },
  DetailActions: { template: '<div><slot/></div>' },
};
const mountPage = () => mount(P4DeliveryTaskDetail, { global: { stubs } });
const recoverBtn = (w: ReturnType<typeof mountPage>) =>
  w.findAll('button').find((b) => b.text() === '触发恢复');

describe('P4DeliveryTaskDetail 失败态恢复 CTA（归位的孤儿门）', () => {
  beforeEach(() => {
    taskRef.value = null;
    sourceRef.value = 'live';
    invokeSpy.mockReset();
  });

  it('失败态 + 部门管理员：渲染「触发恢复」并以 task_id 调 delivery.trigger_recovery', async () => {
    taskRef.value = { status: 'failed', name: 'X' };
    setProductRole('ROLE_ORGAN_MANAGER');
    const w = mountPage();
    const btn = recoverBtn(w);
    expect(btn).toBeTruthy();
    await btn!.trigger('click');
    expect(invokeSpy).toHaveBeenCalledWith(
      expect.objectContaining({ skillId: 'delivery.trigger_recovery', payload: { task_id: 'D-1' } }),
    );
  });

  it('失败态 + 无权岗位（部门操作员）：恢复按钮不渲染（无权=不可见）', () => {
    taskRef.value = { status: 'failed', name: 'X' };
    setProductRole('ROLE_ORGAN_OPERATER');
    expect(recoverBtn(mountPage())).toBeFalsy();
  });

  it('非失败态 + 部门管理员：恢复按钮不渲染（状态门只在 failed 开）', () => {
    taskRef.value = { status: 'warning', name: 'X' };
    setProductRole('ROLE_ORGAN_MANAGER');
    expect(recoverBtn(mountPage())).toBeFalsy();
  });
});
