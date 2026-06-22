import { describe, it, expect } from 'vitest';
import {
  providerLifecycleBucket,
  providerLifecycleLabel,
  providerResourceRows,
  providerCatalogRows,
} from './providerProjection';

// 档 B 承重守护：供数侧「资源/目录管理清单」行「查看」须指向**独立供数详情路由**
// /provider/resource|catalog（供数管理视角、走供数角色门）。若被改回消费路由 /discovery/...，
// 供数方点自己资源又会落消费框架 + 业务运营员被弹回工作台（错配复发），故钉死回归守护。
describe('供数清单「查看」指向供数详情路由', () => {
  it('资源行：viewHref 指向 /provider/resource/:id（非消费 /discovery）', () => {
    const rows = providerResourceRows({
      resources: [{ id: 'r-1', name: '历年GDP信息', lifecycle_status: 'draft' }],
    });
    expect(rows[0].viewHref).toBe('#/provider/resource/r-1');
    expect(rows[0].viewHref).not.toContain('/discovery/');
  });

  it('目录行：viewHref 指向 /provider/catalog/:code（非消费 /discovery）', () => {
    const rows = providerCatalogRows({
      catalogs: [{ catalog_code: 'C-1', name: '人口库', lifecycle_status: 'active' }],
    });
    expect(rows[0].viewHref).toBe('#/provider/catalog/C-1');
    expect(rows[0].viewHref).not.toContain('/discovery/');
  });

  it('空 id/code：viewHref 为空（不造死链）', () => {
    expect(providerResourceRows({ resources: [{ name: '无标识' }] })[0].viewHref).toBe('');
    expect(providerCatalogRows({ catalogs: [{ name: '无码' }] })[0].viewHref).toBe('');
  });
});

describe('provider lifecycle display helpers', () => {
  it('把 active/published 统一识别为已发布桶', () => {
    expect(providerLifecycleBucket('active')).toBe('published');
    expect(providerLifecycleBucket('published')).toBe('published');
    expect(providerLifecycleBucket('已发布')).toBe('published');
    expect(providerLifecycleLabel('active')).toBe('已发布');
  });

  it('把平台审核机器态保留为具体中文展示', () => {
    expect(providerLifecycleBucket('pending_platform_review')).toBe('reviewing');
    expect(providerLifecycleLabel('pending_platform_review')).toBe('平台审核中');
  });
});
