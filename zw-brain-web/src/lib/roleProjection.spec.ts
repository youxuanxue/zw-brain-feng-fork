import { describe, it, expect } from 'vitest';
import type { Snapshot } from '@/composables/useSnapshot';
import { myGrants, myRequests, bucketForRequest } from './roleProjection';

// 缺陷 1 / 客户 0604 反馈下半截：三视图按 mine 收口到本人。
// 快照 requests 经后端部门收口后，含同部门他人的授权 + 本部门入站单（mine=false），
// 「我的申请」与「我的授权」都必须按 mine 过滤，否则用户进到不属于自己的页面 = 越权可见。

// 构造一个仅含 requests 的最小快照（其余字段本层不读，断言只看三视图分流）。
function makeSnapshot(requests: unknown[]): Snapshot {
  return { workbench: {}, discovery: {}, requests };
}

// granted ∈ GRANT_STATUSES → 落 'grant' 桶（「我的授权」）。
const myGrant = { id: 'g-mine', status: 'granted', mine: true };
// 同部门他人的授权（mine=false）：grant 桶但不属于本人，不应进「我的授权」。
const otherGrant = { id: 'g-other', status: 'granted', mine: false };
// submitted ∈ INFLIGHT_STATUSES → 落 'inflight' 桶（「我的申请」），mine=true。
const myInflight = { id: 'r-mine', status: 'submitted', mine: true };

describe('角色投影三视图按 mine 收口', () => {
  it('bucketForRequest：授权态落 grant 桶、在途态落 inflight 桶', () => {
    expect(bucketForRequest(myGrant)).toBe('grant');
    expect(bucketForRequest(otherGrant)).toBe('grant');
    expect(bucketForRequest(myInflight)).toBe('inflight');
  });

  it('myGrants 只返回 mine=true 的 grant 条（过滤掉同部门他人授权）', () => {
    const snapshot = makeSnapshot([myGrant, otherGrant, myInflight]);
    const cards = myGrants(snapshot);
    expect(cards.map((c) => c.id)).toEqual(['g-mine']);
  });

  it('mine=false 的 grant 条不进「我的授权」（越权可见回归守卫）', () => {
    const snapshot = makeSnapshot([otherGrant]);
    expect(myGrants(snapshot)).toEqual([]);
  });

  it('myRequests 只返回 mine=true 的非 grant 条（授权态归「我的授权」不重复）', () => {
    const snapshot = makeSnapshot([myGrant, otherGrant, myInflight]);
    const cards = myRequests(snapshot);
    expect(cards.map((c) => c.id)).toEqual(['r-mine']);
  });

  it('空快照 → 两视图诚实空', () => {
    expect(myGrants(null)).toEqual([]);
    expect(myRequests(makeSnapshot([]))).toEqual([]);
  });
});
