import { test, expect } from '@playwright/test';
import {
  E2E_BASE_URL,
  gotoHash,
  setRole,
  skipUnlessBackend,
  waitAppReady,
} from './helpers';

/**
 * 部门数据隔离 真·双账号浏览器 e2e（真浏览器、两个不同部门会话同栈并存）。
 *
 * 证明用户最初反馈的缺陷已修：此前所有用户登录后看到的资源/目录都一样，与所属部门无关。
 * 现两个不同部门的**部门管理员**各自登录（cookie 会话钉不同机构）→ 供数侧「目录管理」
 * （system.snapshot.provider.catalogs，经真实会话部门收口）**互不相交**，全局角色见全量。
 *
 * 使能改动：dev-bypass-login 接受可选 ?org=<机构码> 覆盖会话机构（仅 dev 档，
 * 已 fail-closed 于 get_dev_iam_bypass_enabled），单栈即可起两个不同部门会话；缺省回落 env。
 *
 * 断言走 catalog **id**（不走 owner_org_id 字面值——legacy 行 owner 可能存机构名而非码，
 * 后端 org_in_scope 读时归一、但卡片 owner_org_id 透传原值；用 id 集合判隔离最稳）。
 */

type APIRequestContext = import('@playwright/test').APIRequestContext;
type BrowserContext = import('@playwright/test').BrowserContext;

const SHOT_DIR = process.env.ZW_E2E_SHOT_DIR || '/tmp/zw-e2e-shots';

/** 全局快照（业务运营员 visible=None 见全量）→ 每个目录的 {id, owner}，用于挑两个有目录的部门。 */
async function allCatalogs(api: APIRequestContext): Promise<Array<{ id: string; owner: string }>> {
  const r = await api.get(`${E2E_BASE_URL}/api/snapshot?role=ROLE_BUSIAUDIT`);
  if (!r.ok()) return [];
  const body = (await r.json()) as Record<string, unknown>;
  const provider = (body.provider ?? {}) as Record<string, unknown>;
  const cats = (provider.catalogs ?? []) as Array<Record<string, unknown>>;
  return cats.map((c) => ({
    id: String(c.id ?? c.catalog_code ?? ''),
    owner: String(c.owner_org_id ?? ''),
  })).filter((c) => c.id);
}

/** 单栈起一个钉指定机构的 dev-bypass cookie 会话（context.request 与 context 页面共享 cookie jar）。 */
async function loginAs(browser: import('@playwright/test').Browser, org: string): Promise<BrowserContext> {
  const ctx = await browser.newContext();
  const resp = await ctx.request.post(
    `${E2E_BASE_URL}/auth/iaf/dev-bypass-login?org=${encodeURIComponent(org)}`,
  );
  expect(resp.ok(), `dev-bypass-login?org=${org} 应成功`).toBeTruthy();
  return ctx;
}

/** 该 cookie 会话（部门管理员）供数目录的 catalog id 集——即页面渲染所据、经真实会话部门收口。 */
async function providerCatalogIds(ctx: BrowserContext): Promise<Set<string>> {
  const r = await ctx.request.get(`${E2E_BASE_URL}/api/snapshot?role=ROLE_ORGAN_MANAGER`);
  expect(r.ok()).toBeTruthy();
  const body = (await r.json()) as Record<string, unknown>;
  const provider = (body.provider ?? {}) as Record<string, unknown>;
  const cats = (provider.catalogs ?? []) as Array<Record<string, unknown>>;
  return new Set(cats.map((c) => String(c.id ?? c.catalog_code ?? '')).filter(Boolean));
}

test.describe('部门数据隔离 真·双账号浏览器', () => {
  test('两个不同部门的部门管理员看到互不相交的供数目录', async ({ page, browser, playwright }, testInfo) => {
    await skipUnlessBackend(page, testInfo);

    // 1) 枚举全局目录，按 owner 分组，挑两个各自有目录的真实部门（排除 platform / 空）。
    const api = await playwright.request.newContext();
    let cats: Array<{ id: string; owner: string }> = [];
    try {
      cats = await allCatalogs(api);
    } finally {
      await api.dispose();
    }
    const byOwner = new Map<string, string[]>();
    for (const c of cats) {
      if (!c.owner || c.owner === 'platform') continue; // platform 非部门
      byOwner.set(c.owner, [...(byOwner.get(c.owner) ?? []), c.id]);
    }
    // 取目录数最多的两个 owner 作两部门——避开「机构名 vs 机构码」别名陷阱（同一机构的名别名
    // 目录数远少于其码本体，永不会进 top-2），确保 orgA/orgB 是两个**真正不同**的部门。
    const deptOwners = [...byOwner.entries()]
      .sort((a, b) => b[1].length - a[1].length)
      .map(([o]) => o);
    test.skip(deptOwners.length < 2, `seed 仅 ${deptOwners.length} 个有目录的部门，无法验跨部门隔离`);
    const [orgA, orgB] = deptOwners.slice(0, 2);
    const repA = byOwner.get(orgA)![0]; // orgA 的一个代表目录 id
    const repB = byOwner.get(orgB)![0];

    // 2) 单栈起两个不同部门的 cookie 会话。
    const ctxA = await loginAs(browser, orgA);
    const ctxB = await loginAs(browser, orgB);
    try {
      // 3) 真 UI 走查：各自登录态打开供数页，证明页面对各账号可达 + 留截图证据。
      for (const [ctx, tag] of [[ctxA, 'orgA'], [ctxB, 'orgB']] as Array<[BrowserContext, string]>) {
        const p = await ctx.newPage();
        await p.goto('/');
        await waitAppReady(p);
        await setRole(p, 'ROLE_ORGAN_MANAGER');
        await gotoHash(p, '#/provider');
        await expect(p.locator('.user-menu-button')).toBeVisible();
        await p.screenshot({ path: `${SHOT_DIR}/dept-iso-${tag}-provider.png`, fullPage: true });
      }

      // 4) 核心断言：两账号供数目录互不相交、各含自机构代表目录、不含对方的。
      const idsA = await providerCatalogIds(ctxA);
      const idsB = await providerCatalogIds(ctxB);
      expect(idsA.size, 'A 部门管理员应见本机构目录').toBeGreaterThan(0);
      expect(idsB.size, 'B 部门管理员应见本机构目录').toBeGreaterThan(0);
      expect(idsA.has(repA), 'A 见本机构代表目录').toBeTruthy();
      expect(idsA.has(repB), 'A **不**见 B 部门代表目录（隔离）').toBeFalsy();
      expect(idsB.has(repB), 'B 见本机构代表目录').toBeTruthy();
      expect(idsB.has(repA), 'B **不**见 A 部门代表目录（隔离）').toBeFalsy();
      const overlap = [...idsA].filter((id) => idsB.has(id));
      expect(overlap, '两部门管理员看到的目录集互不相交（正是用户反馈缺失的隔离）').toEqual([]);
    } finally {
      await ctxA.close();
      await ctxB.close();
    }
  });
});
