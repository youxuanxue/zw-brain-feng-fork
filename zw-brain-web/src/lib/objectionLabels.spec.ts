import { describe, expect, it } from 'vitest';
import { objectionTargetHref, providerObjectionTargetHref } from './objectionLabels';

describe('objectionTargetHref', () => {
  it('消费侧 resource/delivery 路由编码含斜杠的 target_id', () => {
    expect(objectionTargetHref('resource', '370000308004000000/000001')).toBe(
      '#/discovery/resource/370000308004000000%2F000001',
    );
    expect(objectionTargetHref('delivery', 'task/with/slash')).toBe(
      '#/delivery-exchange/task/task%2Fwith%2Fslash',
    );
  });

  it('未知对象类型不生成死链', () => {
    expect(objectionTargetHref('catalog', 'x-1')).toBeUndefined();
    expect(objectionTargetHref('resource', '')).toBeUndefined();
  });
});

describe('providerObjectionTargetHref', () => {
  it('供数侧异议详情可以跳回目录管理详情，并编码目录码', () => {
    expect(providerObjectionTargetHref('catalog', '370000308004000000/000001')).toBe(
      '#/provider/catalog/370000308004000000%2F000001',
    );
  });

  it('供数侧异议详情可以跳回资源管理详情', () => {
    expect(providerObjectionTargetHref('resource', 'res-1')).toBe('#/provider/resource/res-1');
  });

  it('交付任务沿用交付详情路由', () => {
    expect(providerObjectionTargetHref('delivery', 'task-1')).toBe('#/delivery-exchange/task/task-1');
  });

  it('未知对象类型不生成死链', () => {
    expect(providerObjectionTargetHref('unknown', 'x-1')).toBeUndefined();
    expect(providerObjectionTargetHref('catalog', '')).toBeUndefined();
  });
});
