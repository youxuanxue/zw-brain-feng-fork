import { describe, it, expect } from 'vitest';
import { mount } from '@vue/test-utils';
import { h } from 'vue';
import GatedAction from './GatedAction.vue';

// canPerformAction('application.dept_approve', role) → 仅 OPERATER/MANAGER 为真（pageAccess SoT）。
const GATE = 'application.dept_approve';
const slot = () => h('span', { class: 'cta' }, '办理');

describe('GatedAction', () => {
  it('有权岗位渲染默认插槽', () => {
    const w = mount(GatedAction, {
      props: { gate: GATE, role: 'ROLE_ORGAN_MANAGER' },
      slots: { default: slot },
    });
    expect(w.find('.cta').exists()).toBe(true);
    expect(w.text()).toContain('办理');
  });

  it('无权岗位什么都不渲染', () => {
    const w = mount(GatedAction, {
      props: { gate: GATE, role: 'ROLE_SECURITY_AUDIT' },
      slots: { default: slot },
    });
    expect(w.find('.cta').exists()).toBe(false);
    expect(w.text()).toBe('');
  });

  it('未登记的 gate 默认放行（后端兜底）', () => {
    const w = mount(GatedAction, {
      props: { gate: 'some.unregistered.capability', role: 'ROLE_SECURITY_AUDIT' },
      slots: { default: slot },
    });
    expect(w.find('.cta').exists()).toBe(true);
  });
});
