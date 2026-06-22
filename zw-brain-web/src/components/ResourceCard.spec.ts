import { describe, expect, it } from 'vitest';
import { mount } from '@vue/test-utils';
import ResourceCard from './ResourceCard.vue';

const baseResource = {
  id: 'res-active-1',
  name: '停车场信息',
  lifecycleStatus: 'active',
  status: '已发布',
};

describe('ResourceCard 详情与申请入口', () => {
  it('申请人 + active：显示发起申请和查看详情', () => {
    const w = mount(ResourceCard, { props: { resource: baseResource, showAction: true } });
    expect(w.get('button[data-skill="request.create"]').text()).toBe('发起申请');
    expect(w.get('a.gov-btn-secondary').text()).toBe('查看详情');
  });

  it('非申请人：仍显示查看详情，不显示发起申请', () => {
    const w = mount(ResourceCard, { props: { resource: baseResource, showAction: false } });
    expect(w.find('button[data-skill="request.create"]').exists()).toBe(false);
    expect(w.get('a.gov-btn-secondary').text()).toBe('查看详情');
  });

  it('非 active：仍显示查看详情，不显示发起申请', () => {
    const w = mount(ResourceCard, {
      props: { resource: { ...baseResource, lifecycleStatus: 'approved_pending_publish' }, showAction: true },
    });
    expect(w.find('button[data-skill="request.create"]').exists()).toBe(false);
    expect(w.get('a.gov-btn-secondary').text()).toBe('查看详情');
  });

  it('召回候选：不显示详情和申请入口', () => {
    const w = mount(ResourceCard, {
      props: {
        resource: { id: 'recall:停车场信息', name: '停车场信息', kind: 'recall_dictionary' },
        showAction: true,
      },
    });
    expect(w.find('button[data-skill="request.create"]').exists()).toBe(false);
    expect(w.find('a.gov-btn-secondary').exists()).toBe(false);
    expect(w.text()).toContain('暂无详情与申请入口');
  });
});
