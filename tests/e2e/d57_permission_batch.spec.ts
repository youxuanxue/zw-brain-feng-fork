// D57 权限/可达性批次（feedback-0611-gate 裁决①②④⑨）真 UI 走查。
//
//   A1（裁决①/R6）业务运营员异议受理面：收件箱纳入 submitted + objection.case.accept 点到底；
//   A2（裁决②/R8）工作台语境四分：安全审计员=监督概览（不再被误归「我的申请进度」）、
//      办理建议真实现算（无 seed 虚构叙事）；
//   A3（裁决④）管理员申请人身份：从找数据详情发起申请走到草稿（双面另见 permission_invisibility）；
//   A6（裁决⑨/R10）管理员挂接审核去盲批：被审登记详情 + 关联资源名 + 驳回带理由。
//
// 铸态一律走无 cookie 的独立 APIRequestContext（带 cookie POST 会触发 CSRF 拦截）。
import { expect, test } from '@playwright/test';
import { E2E_BASE_URL, gotoHash, setRole, skipUnlessBackend, waitAppReady } from './helpers';

async function invoke(
  api: import('@playwright/test').APIRequestContext,
  skill: string,
  data: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const resp = await api.post(`${E2E_BASE_URL}/api/skills/${skill}`, { data });
  const body = (await resp.json().catch(() => ({}))) as Record<string, unknown>;
  return (body.result ?? body) as Record<string, unknown>;
}

test.describe('D57 权限批次走查', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    await page.goto(E2E_BASE_URL);
    await waitAppReady(page);
  });

  test('A1 异议受理链：submitted 进收件箱 → 业务运营员「受理」点到底 → 进入核查', async ({ page, playwright }) => {
    test.setTimeout(120_000);
    const api = await playwright.request.newContext();
    const runTag = Date.now().toString(36);
    const title = `e2e D57 待受理异议-${runTag}`;
    let objectionId = '';
    try {
      const q = await invoke(api, 'catalog.entry.query', { role: 'ROLE_ORGAN_OPERATER', limit: 1, confirmed: true });
      const items = (q.items ?? []) as Array<Record<string, unknown>>;
      const code = String(items[0]?.catalog_code ?? '');
      test.skip(!code, '真实库无目录可挂异议');
      const created = await invoke(api, 'objection.case.create', {
        target_type: 'catalog',
        target_id: code,
        title,
        role: 'ROLE_ORGAN_OPERATER',
        confirmed: true,
      });
      objectionId = String(created.id ?? '');
      if (objectionId) {
        await invoke(api, 'objection.case.submit', {
          objection_id: objectionId,
          role: 'ROLE_ORGAN_OPERATER',
          confirmed: true,
        });
      }
    } finally {
      await api.dispose();
    }
    test.skip(!objectionId, '铸 submitted 异议失败');

    // 独立 APIRequestContext 铸态后浏览器 snapshot 可能仍停留在登录期预取；reload 对齐真实审核会话。
    await page.reload();
    await waitAppReady(page);

    // 业务运营员收件箱：submitted 行可见 + 「受理」按钮可点（修复前收件箱只列 provider_investigating，
    // 待受理案件在唯一工作面不可见）。
    await setRole(page, 'ROLE_BUSIAUDIT');
    await gotoHash(page, '#/provider/inbox/objection');
    const row = page.locator('tr[data-testid="objection-inbox-row"]', { hasText: title });
    await expect(row).toHaveCount(1, { timeout: 15_000 });
    const acceptBtn = row.getByTestId('objection-accept-btn');
    await expect(acceptBtn).toBeVisible();
    await acceptBtn.click();
    // 受理点到底：按钮消失（状态离开 submitted）、行保留在收件箱（核查中，不消失成死端）。
    await expect(acceptBtn).toHaveCount(0, { timeout: 15_000 });
    await expect(row, '受理后案件应保留在收件箱（平台核查中）').toHaveCount(1);
  });

  test('A2 工作台语境：审计员=监督概览（非申请进度）、操作员=申请进度、办理建议无虚构叙事', async ({ page }) => {
    test.setTimeout(120_000);
    // 安全审计员：监督概览语境 + 只读指引（修复前 isApplicantOnly 二分误归「我的申请进度」）。
    await setRole(page, 'ROLE_SECURITY_AUDIT');
    await gotoHash(page, '#/workbench');
    await expect(page.getByRole('heading', { name: '监督概览' })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole('heading', { name: '我的申请进度' })).toHaveCount(0);
    await expect(page.locator('body')).not.toContainText('停车场信息共享目录');
    await expect(page.locator('body')).not.toContainText('绕开模板');

    // 平台运维员：运维核查语境。
    await setRole(page, 'ROLE_SYSTEM');
    await gotoHash(page, '#/workbench');
    await expect(page.getByRole('heading', { name: '运维核查' })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole('heading', { name: '我的申请进度' })).toHaveCount(0);

    // 部门操作员：申请进度形态保持（0609 docx），办理建议不再渲染 seed 虚构「黄金旅程」叙事。
    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, '#/workbench');
    await expect(page.getByRole('heading', { name: '我的申请进度' })).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('body')).not.toContainText('黄金旅程');
    await expect(page.locator('body')).not.toContainText('停车场信息共享目录复用申请');
  });

  test('A3 管理员申请人身份：从找数据详情发起申请走到草稿，三分栏不混', async ({ page }) => {
    test.setTimeout(120_000);
    const snap = await page.request.get(`${E2E_BASE_URL}/api/snapshot?role=ROLE_ORGAN_MANAGER`);
    test.skip(!snap.ok(), 'snapshot unavailable');
    const body = (await snap.json()) as Record<string, unknown>;
    const discovery = (body.discovery ?? {}) as Record<string, unknown>;
    const resources = (discovery.resources ?? []) as Array<Record<string, unknown>>;
    const resId = String(resources[0]?.id ?? '');
    test.skip(!resId, 'no discovery.resources row');

    await setRole(page, 'ROLE_ORGAN_MANAGER');
    await gotoHash(page, `#/discovery/resource/${encodeURIComponent(resId)}`);
    const applyBtn = page.locator('button[data-skill="request.create"]');
    await expect(applyBtn, 'D57④：管理员发起入口补回').toBeVisible({ timeout: 15_000 });
    await applyBtn.click();
    await page.waitForURL(/#\/request-flow\/request\//, { timeout: 15_000 });
    const reqId = decodeURIComponent(page.url().split('/request-flow/request/')[1] ?? '').split('?')[0];
    expect(reqId, '管理员发起申请应落草稿并跳详情').toBeTruthy();

    // IA 重构（拆「办申请」）：消费方「我的申请」归并领数据（#/delivery-exchange）；管理员作为申请人
    // 在领数据见「我的申请」视图（视图只回答一个问题，受理/审核已迁工作台行内、不混进我的申请）。
    await gotoHash(page, '#/delivery-exchange');
    await expect(page.getByTestId('p4-view-mine')).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId('p4-pane-mine')).toBeVisible();
  });

  test('A6 挂接审核去盲批：被审详情可见、关联资源/目录名非「—」、驳回带理由点到底', async ({ page, playwright }) => {
    test.setTimeout(150_000);
    const api = await playwright.request.newContext();
    const runTag = Date.now().toString(36);
    const resCode = `res-e2e-d57-${runTag}`;
    const title = `e2e D57 挂接待审-${runTag}`;
    let minted = false;
    try {
      const q = await invoke(api, 'catalog.entry.query', { role: 'ROLE_ORGAN_OPERATER', limit: 1, confirmed: true });
      const items = (q.items ?? []) as Array<Record<string, unknown>>;
      const catalogCode = String(items[0]?.catalog_code ?? '');
      const prepared = await invoke(api, 'resource.mount.file.prepare', {
        resource_code: resCode,
        catalog_code: catalogCode || undefined,
        title,
        owner_org_id: '11370000MB284651XL',
        file_name: 'd57.csv',
        access_path: `/data/d57-${runTag}.csv`,
        content_hash: 'sha256:d57',
        update_frequency: 'daily',
        resource_desc: 'D57 e2e 挂接登记信息',
        shared_type: '2',
        role: 'ROLE_ORGAN_OPERATER',
        confirmed: true,
      });
      if (prepared && (prepared.resource_code || prepared.content_fingerprint)) {
        const submitted = await invoke(api, 'resource.asset.submit_review', {
          resource_code: resCode,
          role: 'ROLE_ORGAN_OPERATER',
          confirmed: true,
        });
        minted = Boolean(submitted);
      }
    } finally {
      await api.dispose();
    }
    test.skip(!minted, '铸挂接待审资源失败');

    await page.reload();
    await waitAppReady(page);

    await setRole(page, 'ROLE_ORGAN_MANAGER');
    await gotoHash(page, '#/provider/inbox/hookup-review');
    const row = page.locator('tr[data-testid="hookup-review-row"]', { hasText: title });
    await expect(row).toHaveCount(1, { timeout: 15_000 });
    // 关联资源列 = 资源名（修复前 resource_name/catalog_name 投影缺失 → 恒「—」）。
    await expect(row).toContainText(title);

    // 被审登记详情：形态/提供方/挂接位置/共享类型/描述行内可见（修复前盲批）。
    await row.getByTestId('hookup-detail-toggle').click();
    const detail = page.getByTestId('hookup-detail-panel');
    await expect(detail).toBeVisible();
    await expect(detail).toContainText('资源形态');
    await expect(detail).toContainText('文件');
    await expect(detail).toContainText('挂接位置');
    await expect(detail).toContainText(`d57-${runTag}`);
    await expect(detail).toContainText('有条件共享');

    // 驳回带理由点到底：填理由 → 确认 → 行从收件箱消失（资源退回提交方整改）。
    await row.getByTestId('hookup-reject-btn').click();
    const rejectPanel = page.getByTestId('hookup-reject-panel');
    await expect(rejectPanel).toBeVisible();
    await rejectPanel.locator('textarea').fill('登记信息缺少数据来源说明，请补全后重新提交');
    await rejectPanel.getByTestId('hookup-reject-confirm-btn').click();
    await expect(row, '驳回后行应离开收件箱').toHaveCount(0, { timeout: 20_000 });

    // 理由闭环（写了就必须有读面）：提交方（操作员）在「资源管理清单」看到驳回理由整改依据。
    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, '#/provider/resources');
    const manageRow = page.locator('[data-testid="provider-resource-list"] tr', { hasText: title });
    await expect(manageRow).toHaveCount(1, { timeout: 15_000 });
    await expect(manageRow.getByTestId('row-status-note')).toContainText('驳回理由：登记信息缺少数据来源说明');
  });
});
