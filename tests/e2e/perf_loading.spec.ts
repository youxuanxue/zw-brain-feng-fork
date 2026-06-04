import { test, expect, type Page, type Request } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname } from 'node:path';
import { E2E_BASE_URL, skipUnlessBackend, waitAppReady } from './helpers';

// 性能 follow-up 实测 spec（#213 半截加载修复的收口；issue #126 复现/验收）。
//
// 本 spec **不 back 任何 .feature**（同 r12_rendered_language.spec），不触发 D46.g 测量重采——
// 纯前端读路径优化的客观度量。
//
// 度量按 role 维度统计 /api/snapshot 与 /api/skills/workbench.view 的请求次数：
//   FU-4 预取（红→绿锚点）：登录就绪后空闲预取兄弟岗位，**每个**可切换岗位的 snapshot+工作台
//     都应在切角色前被预热（RED：兄弟岗位直到被切到才首次拉取 → 预热计数为 0）。
//   FU-1 并发去重：当前岗位的 boot 拉取不应放大成多次在途重复（≤2：首拉 + 至多一次 SWR 校验）。
//   同岗位换页：本地缓存渲染，0 次重拉（#213 SWR 已具备，守卫不回退）。
// 切角色感知耗时与各项计数落 perf-metrics JSON，供 D37 BEFORE/AFTER 证据对比。

const METRICS_OUT = process.env.ZW_PERF_METRICS_OUT ?? '/tmp/perf_loading_metrics.json';

interface RoleTally {
  workbenchView: number;
  snapshot: number;
}

function roleFromUrl(url: string): string {
  const m = /[?&]role=([^&]+)/.exec(url);
  return m ? decodeURIComponent(m[1]) : '';
}

/** 安装按 role 维度的请求计数器。 */
function installRoleCounter(page: Page): Map<string, RoleTally> {
  const byRole = new Map<string, RoleTally>();
  const bump = (role: string, kind: keyof RoleTally) => {
    const t = byRole.get(role) ?? { workbenchView: 0, snapshot: 0 };
    t[kind] += 1;
    byRole.set(role, t);
  };
  page.on('request', (req: Request) => {
    const url = req.url();
    if (url.includes('/api/skills/workbench.view')) bump(roleFromUrl(url), 'workbenchView');
    else if (url.includes('/api/snapshot')) bump(roleFromUrl(url), 'snapshot');
  });
  return byRole;
}

function tally(byRole: Map<string, RoleTally>, role: string): RoleTally {
  return byRole.get(role) ?? { workbenchView: 0, snapshot: 0 };
}

/** 等工作台真正 ready：P1 hero（v-if="data"）可见即数据到位。 */
async function waitWorkbenchReady(page: Page, timeout = 20_000): Promise<number> {
  const t0 = Date.now();
  await page.locator('.p1-hero').first().waitFor({ state: 'visible', timeout });
  return Date.now() - t0;
}

async function siblingRoles(page: Page): Promise<{ current: string; others: string[] }> {
  await page.waitForSelector('#role-switch', { timeout: 20_000 });
  return page.evaluate(() => {
    const sel = document.querySelector('#role-switch') as HTMLSelectElement | null;
    if (!sel) return { current: '', others: [] as string[] };
    const all = Array.from(sel.options).map((o) => o.value);
    return { current: sel.value, others: all.filter((v) => v !== sel.value) };
  });
}

test.describe('perf: 加载与切角色读路径', () => {
  test('兄弟岗位预热 + 当前岗位去重 + 各页首屏不退化', async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);

    const metrics: Record<string, unknown> = {
      baseUrl: E2E_BASE_URL,
      capturedAt: new Date().toISOString(),
    };
    const byRole = installRoleCounter(page);

    // ---------- 阶段 A：boot ----------
    const tBootStart = Date.now();
    await page.goto('/');
    await waitAppReady(page);
    const bootReadyMs = await waitWorkbenchReady(page);
    const { current, others } = await siblingRoles(page);

    // ---------- 阶段 B：等预取就绪（兄弟岗位空闲预取 settle）----------
    // 预取可能在 boot 即触发或随空闲回调稍后到；统一等网络静默 + 上限兜底。
    await page.waitForLoadState('networkidle', { timeout: 6_000 }).catch(() => undefined);
    await page.waitForTimeout(1_500);

    const cur = tally(byRole, current);
    const prefetchCoverage = others.map((r) => {
      const t = tally(byRole, r);
      return { role: r, snapshot: t.snapshot, workbenchView: t.workbenchView };
    });
    metrics.boot = { readyMs: bootReadyMs, totalMs: Date.now() - tBootStart };
    metrics.currentRole = { role: current, snapshot: cur.snapshot, workbenchView: cur.workbenchView };
    metrics.siblingPrefetch = { count: others.length, coverage: prefetchCoverage };

    // ---------- 阶段 C：切到兄弟岗位（应命中预取缓存秒显）----------
    const switchMetrics: Array<Record<string, unknown>> = [];
    for (const role of others.slice(0, 2)) {
      const tSw = Date.now();
      await page.selectOption('#role-switch', role);
      await expect(page.locator('#role-switch')).toHaveValue(role);
      const readyMs = await waitWorkbenchReady(page);
      switchMetrics.push({ role, readyMs, wallMs: Date.now() - tSw });
    }
    metrics.roleSwitch = switchMetrics;

    // ---------- 阶段 D：同岗位各页首屏（本地缓存渲染，应无 API）----------
    const pages = ['#/discovery', '#/request-flow', '#/delivery', '#/provider'];
    const pageMetrics: Array<Record<string, unknown>> = [];
    for (const hash of pages) {
      const beforeAll = [...byRole.values()].reduce(
        (a, t) => ({ wb: a.wb + t.workbenchView, snap: a.snap + t.snapshot }),
        { wb: 0, snap: 0 },
      );
      const tp = Date.now();
      await page.evaluate((h) => {
        if (window.location.hash === h) window.location.hash = '#/__nav_reset__';
      }, hash);
      await page.evaluate((h) => {
        window.location.hash = h;
      }, hash);
      await page.locator('#app-router').first().waitFor({ state: 'visible', timeout: 10_000 });
      const afterAll = [...byRole.values()].reduce(
        (a, t) => ({ wb: a.wb + t.workbenchView, snap: a.snap + t.snapshot }),
        { wb: 0, snap: 0 },
      );
      pageMetrics.push({
        hash,
        ms: Date.now() - tp,
        snapshotDelta: afterAll.snap - beforeAll.snap,
        workbenchViewDelta: afterAll.wb - beforeAll.wb,
      });
    }
    metrics.pageNav = pageMetrics;

    // ---------- 落盘 + 打印（D37 证据）----------
    mkdirSync(dirname(METRICS_OUT), { recursive: true });
    writeFileSync(METRICS_OUT, JSON.stringify(metrics, null, 2));
    // eslint-disable-next-line no-console
    console.log('[perf-metrics]\n' + JSON.stringify(metrics, null, 2));

    // ---------- 硬不变量 ----------
    // (A) FU-4 红→绿锚点：每个可切换兄弟岗位在切角色前都被预热（snapshot + 工作台各 ≥1）。
    //     RED 无预取 → 兄弟岗位计数为 0；GREEN 预取后 ≥1，切角色即命中缓存秒显（SWR 仍后台校验）。
    if (current && others.length > 0) {
      for (const cov of prefetchCoverage) {
        expect(cov.snapshot, `兄弟岗位 ${cov.role} 应被预热 snapshot`).toBeGreaterThanOrEqual(1);
        expect(cov.workbenchView, `兄弟岗位 ${cov.role} 应被预热 workbench`).toBeGreaterThanOrEqual(1);
      }
    }

    // (B) FU-1 当前岗位去重守卫：boot 期当前岗位拉取不放大成在途重复
    //     （首拉 + 至多一次 SWR 校验；并发触发被 _inflight 合并）。
    expect(cur.workbenchView, '当前岗位 boot workbench.view 不应放大重复').toBeLessThanOrEqual(2);
    expect(cur.snapshot, '当前岗位 boot snapshot 不应放大重复').toBeLessThanOrEqual(2);

    // (D) 同岗位各页切换不触发 snapshot/workbench 重拉（本地缓存渲染，守卫不回退）。
    for (const pm of pageMetrics) {
      expect(pm.snapshotDelta as number, `${pm.hash} 同岗位切换不应重拉 snapshot`).toBe(0);
      expect(pm.workbenchViewDelta as number, `${pm.hash} 同岗位切换不应重拉 workbench`).toBe(0);
    }
  });
});
