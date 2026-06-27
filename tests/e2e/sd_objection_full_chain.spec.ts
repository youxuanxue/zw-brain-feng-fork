import { expect, test, type APIRequestContext, type Page } from '@playwright/test';
import {
  E2E_BASE_URL,
  firstCatalogCode,
  gotoHash,
  setRole,
  skipUnlessBackend,
  waitAppReady,
} from './helpers';

type DemandRecord = {
  id?: string;
  title?: string;
  response_status?: string;
  provider_decision?: string;
  provider_response_note?: string;
  provider_resource_ref?: string;
};

type ObjectionRecord = {
  id?: string;
  title?: string;
  status?: string;
};

const ALL_ROLES = [
  'ROLE_ORGAN_OPERATER',
  'ROLE_ORGAN_MANAGER',
  'ROLE_BUSIAUDIT',
  'ROLE_SECURITY_AUDIT',
  'ROLE_SYSTEM',
] as const;

async function invokeSkill(
  api: APIRequestContext,
  skill: string,
  data: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const resp = await api.post(`${E2E_BASE_URL}/api/skills/${skill}`, { data });
  expect(resp.ok(), await resp.text()).toBeTruthy();
  const body = (await resp.json().catch(() => ({}))) as Record<string, unknown>;
  return (body.result ?? body) as Record<string, unknown>;
}

async function queryDemands(api: APIRequestContext, title: string): Promise<DemandRecord[]> {
  const resp = await api.post(`${E2E_BASE_URL}/api/skills/demand.list`, {
    data: { role: 'ROLE_ORGAN_MANAGER', confirmed: true },
  });
  expect(resp.ok(), await resp.text()).toBeTruthy();
  const body = (await resp.json()) as { items?: DemandRecord[] };
  return (body.items ?? []).filter((item) => item.title === title);
}

async function waitForDemand(
  api: APIRequestContext,
  title: string,
  predicate: (record: DemandRecord) => boolean,
): Promise<DemandRecord> {
  for (let i = 0; i < 30; i += 1) {
    const hit = (await queryDemands(api, title)).find(predicate);
    if (hit) return hit;
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`demand did not reach expected state: ${title}`);
}

async function queryObjection(api: APIRequestContext, id: string): Promise<ObjectionRecord | null> {
  const resp = await api.post(`${E2E_BASE_URL}/api/skills/objection.case.query`, {
    data: { role: 'ROLE_BUSIAUDIT', confirmed: true },
  });
  expect(resp.ok(), await resp.text()).toBeTruthy();
  const body = (await resp.json()) as { items?: ObjectionRecord[] };
  return (body.items ?? []).find((item) => item.id === id) ?? null;
}

async function registerDemand(api: APIRequestContext, title: string): Promise<string> {
  const created = await invokeSkill(api, 'demand.register', {
    role: 'ROLE_ORGAN_OPERATER',
    confirmed: true,
    title,
    target_resource_hint: '低保对象数据',
    applicant_dept: 'E2E 申请部门',
  });
  const id = String(created.id ?? created.demand_id ?? '');
  expect(id).toBeTruthy();
  return id;
}

async function createSubmittedObjection(
  api: APIRequestContext,
  catalogCode: string,
  title: string,
): Promise<string> {
  const created = await invokeSkill(api, 'objection.case.create', {
    role: 'ROLE_ORGAN_OPERATER',
    confirmed: true,
    objection_kind: 'catalog_quality',
    target_type: 'catalog',
    target_id: catalogCode,
    title,
    basis_text: 'E2E 角色矩阵：目录字段说明与底册不一致。',
    evidence: [{ evidence_type: 'catalog', content_json: { source: 'e2e-role-matrix' } }],
  });
  const id = String(created.id ?? created.objection_id ?? '');
  expect(id).toBeTruthy();
  await invokeSkill(api, 'objection.case.submit', {
    role: 'ROLE_ORGAN_OPERATER',
    confirmed: true,
    objection_id: id,
  });
  return id;
}

async function acceptObjection(api: APIRequestContext, id: string): Promise<void> {
  await invokeSkill(api, 'objection.case.accept', {
    role: 'ROLE_BUSIAUDIT',
    confirmed: true,
    objection_id: id,
  });
}

async function returnObjectionForProvider(api: APIRequestContext, id: string): Promise<void> {
  await invokeSkill(api, 'objection.case.review', {
    role: 'ROLE_BUSIAUDIT',
    confirmed: true,
    objection_id: id,
    decision: 'return',
    resolved_summary: '请责任部门补充核查。',
  });
}

async function waitForObjectionStatus(
  api: APIRequestContext,
  id: string,
  status: string,
): Promise<ObjectionRecord> {
  for (let i = 0; i < 30; i += 1) {
    const hit = await queryObjection(api, id);
    if (hit?.status === status) return hit;
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`objection ${id} did not reach ${status}`);
}

function caseIdFromHash(page: Page): string {
  const raw = new URL(page.url()).hash.split('/').pop() ?? '';
  return decodeURIComponent(raw);
}

test.describe('供需对接与异议全链路走查', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    await page.goto('/');
    await waitAppReady(page);
  });

  test('供需对接：需求方登记、提供方响应、需求方可见结果', async ({ page, playwright }) => {
    const api = await playwright.request.newContext();
    const tag = Date.now().toString(36);
    const title = `E2E全链路供需-${tag}`;
    const hint = '低保对象数据';
    const resourceRef = `catalog-e2e-${tag}`;

    try {
      await setRole(page, 'ROLE_ORGAN_OPERATER');
      await gotoHash(page, '#/request-flow/supply-demand');
      await expect(page.getByRole('heading', { name: '领数据' })).toBeVisible();
      await expect(page.getByRole('heading', { name: '我的需求' })).toBeVisible();
      await page.locator('#demand-title').fill(title);
      await page.locator('#demand-hint').fill(hint);
      await page.getByRole('button', { name: '登记需求' }).click();
      await expect(page.locator('.toast-stack')).toContainText('需求已登记');

      const applicantRow = page.locator('.focus-table tbody tr', { hasText: title });
      await expect(applicantRow).toHaveCount(1);
      await expect(applicantRow).toContainText('待响应');
      await applicantRow.click();
      await expect(page.locator('.detail-workspace')).toContainText('待响应');

      await setRole(page, 'ROLE_ORGAN_MANAGER');
      await gotoHash(page, '#/provider/inbox/demand-match');
      await expect(page.getByRole('heading', { name: '供需对接收件箱' })).toBeVisible();
      const inboxRow = page.locator('.focus-table tbody tr', { hasText: title });
      await expect(inboxRow).toHaveCount(1);
      await expect(inboxRow).toContainText('待响应');
      await inboxRow.getByRole('link', { name: '对接' }).click();
      await expect(page.getByRole('heading', { name: title })).toBeVisible();
      await expect(page.getByRole('button', { name: '确认提供' })).toBeVisible();
      await page.locator('#resource-ref').fill(resourceRef);
      await page.locator('#response-note').fill('经核查可提供该类数据，按需对接目录资源。');
      await page.getByRole('button', { name: '确认提供' }).click();
      await expect(page.locator('.toast-stack')).toContainText('已确认提供');
      await expect(page.getByRole('heading', { name: title })).toBeVisible();
      await expect(page.locator('.focus-empty')).toHaveCount(0);
      await expect(page.locator('.panel')).toContainText('已响应');
      await expect(page.locator('.panel')).toContainText('确认提供');
      await expect(page.locator('.panel')).toContainText(resourceRef);
      await expect(page.getByRole('button', { name: '确认提供' })).toHaveCount(0);

      const responded = await waitForDemand(
        api,
        title,
        (record) =>
          record.response_status === 'responded' &&
          record.provider_decision === 'provide' &&
          record.provider_resource_ref === resourceRef,
      );
      expect(responded.provider_response_note).toContain('经核查可提供');

      await setRole(page, 'ROLE_ORGAN_OPERATER');
      await gotoHash(page, '#/request-flow/supply-demand');
      const finalRow = page.locator('.focus-table tbody tr', { hasText: title });
      await expect(finalRow).toHaveCount(1);
      await expect(finalRow).toContainText('已响应');
      await finalRow.click();
      const detail = page.locator('.detail-workspace');
      await expect(detail).toContainText('已响应');
      await expect(detail).toContainText('确认提供');
      await expect(detail).toContainText(resourceRef);
      await expect(page.getByRole('button', { name: '确认完成' })).toBeVisible();
      await page.getByRole('button', { name: '确认完成' }).click();
      await expect(page.locator('.toast-stack')).toContainText('需求已关闭');
      await expect(detail).toContainText('已关闭');
      await expect(detail).toContainText('需求已关闭，供需对接完成。');

      await waitForDemand(api, title, (record) => record.response_status === 'closed');
    } finally {
      await api.dispose();
    }
  });

  test('异议：提交、受理、部门核查、平台确认、评价、归档', async ({ page, playwright }) => {
    const api = await playwright.request.newContext();
    const catalogCode = await firstCatalogCode(api);
    test.skip(!catalogCode, 'no catalog row available in DB to anchor objection');

    const tag = Date.now().toString(36);
    const title = `E2E全链路异议-${tag}`;
    let objectionId = '';

    try {
      await setRole(page, 'ROLE_ORGAN_OPERATER');
      await gotoHash(page, '#/request-flow/objection/new');
      await expect(page.getByRole('heading', { name: '发起异议' })).toBeVisible();
      await page.locator('#title').fill(title);
      await page.locator('#target').fill(catalogCode!);
      await page.locator('#basis').fill('目录字段说明与业务底册不一致，需平台核查并给出处理结论。');
      await page.getByRole('button', { name: '创建异议' }).click();
      await page.waitForURL(
        (url) => /^#\/request-flow\/objection\/[^/]+$/.test(url.hash) && !url.hash.endsWith('/new'),
      );
      objectionId = caseIdFromHash(page);
      expect(objectionId).toBeTruthy();
      await expect(page.getByRole('button', { name: '提交至平台' })).toBeVisible();
      await page.getByRole('button', { name: '提交至平台' }).click();
      await expect(page.locator('.toast-stack')).toContainText('异议已提交');
      await waitForObjectionStatus(api, objectionId, 'submitted');

      await page.reload();
      await waitAppReady(page);
      await setRole(page, 'ROLE_BUSIAUDIT');
      await gotoHash(page, '#/provider/inbox/objection');
      await expect(page.getByRole('heading', { name: '异议响应收件箱' })).toBeVisible();
      const inboxRow = page.getByTestId('objection-inbox-row').filter({ hasText: title });
      await expect(inboxRow).toHaveCount(1);
      await expect(inboxRow).toContainText('已提交');
      await expect(inboxRow.getByTestId('objection-accept-btn')).toBeVisible();
      await inboxRow.getByTestId('objection-accept-btn').click();
      await expect(page.locator('.toast-stack')).toContainText('已受理');
      await waitForObjectionStatus(api, objectionId, 'platform_investigating');

      await gotoHash(page, `#/provider/inbox/objection/${encodeURIComponent(objectionId)}`);
      await expect(page.getByRole('heading', { name: `异议 ${objectionId}` })).toBeVisible();
      await expect(page.locator('#opinion')).toBeVisible();
      await expect(page.getByRole('button', { name: '确认解决' })).toBeVisible();
      await page.locator('#opinion').fill('已受理，需责任部门补充核查依据后再确认。');
      await page.getByRole('button', { name: '退回核查' }).click();
      await expect(page.locator('.toast-stack')).toContainText('已退回继续核查');
      await waitForObjectionStatus(api, objectionId, 'provider_investigating');

      await setRole(page, 'ROLE_ORGAN_MANAGER');
      await gotoHash(page, `#/provider/inbox/objection/${encodeURIComponent(objectionId)}`);
      await expect(page.getByRole('heading', { name: `异议 ${objectionId}` })).toBeVisible();
      await expect(page.locator('#opinion')).toBeVisible();
      await expect(page.getByRole('button', { name: '提交核查回复' })).toBeVisible();
      await page.locator('#opinion').fill('责任部门已核查：字段说明已确认需修正，建议平台确认解决。');
      await page.getByRole('button', { name: '提交核查回复' }).click();
      await expect(page.locator('.toast-stack')).toContainText('已提交提供方回复');
      await waitForObjectionStatus(api, objectionId, 'platform_investigating');

      await setRole(page, 'ROLE_BUSIAUDIT');
      await gotoHash(page, `#/provider/inbox/objection/${encodeURIComponent(objectionId)}`);
      await expect(page.getByRole('button', { name: '确认解决' })).toBeVisible();
      await page.locator('#opinion').fill('平台确认处理结论，异议问题已解决。');
      await page.getByRole('button', { name: '确认解决' }).click();
      await expect(page.locator('.toast-stack')).toContainText('异议已标记为已解决');
      await waitForObjectionStatus(api, objectionId, 'resolved');

      await setRole(page, 'ROLE_ORGAN_OPERATER');
      await gotoHash(page, `#/request-flow/objection/${encodeURIComponent(objectionId)}`);
      await expect(page.getByRole('heading', { name: `异议 ${objectionId}` })).toBeVisible();
      await expect(page.getByRole('button', { name: '提交评价' })).toBeVisible();
      await page.locator('#score').fill('5');
      await page.locator('#comment').fill('处理链路完整，责任部门回复清楚。');
      await page.getByRole('button', { name: '提交评价' }).click();
      await expect(page.locator('.toast-stack')).toContainText('评价已提交');
      await waitForObjectionStatus(api, objectionId, 'resolved');

      await setRole(page, 'ROLE_BUSIAUDIT');
      await gotoHash(page, `#/request-flow/objection/${encodeURIComponent(objectionId)}`);
      await expect(page.getByRole('button', { name: '归档关闭' })).toBeVisible();
      await page.getByRole('button', { name: '归档关闭' }).click();
      await expect(page.locator('.toast-stack')).toContainText('异议已归档');
      await waitForObjectionStatus(api, objectionId, 'closed');
    } finally {
      await api.dispose();
    }
  });

  test('供需对接角色矩阵：5 个岗位的页面与操作权限正确', async ({ page, playwright }) => {
    const api = await playwright.request.newContext();
    const title = `E2E供需角色矩阵-${Date.now().toString(36)}`;
    let demandId = '';
    try {
      demandId = await registerDemand(api, title);
      await waitForDemand(api, title, (record) => record.response_status === 'pending_response');
    } finally {
      await api.dispose();
    }

    for (const role of ALL_ROLES) {
      await setRole(page, role);
      await gotoHash(page, '#/request-flow/supply-demand');
      const deliveryHeading = page.getByRole('heading', { name: '领数据' });
      const supplyHeading = page.getByRole('heading', { name: '我的需求' });
      const registerButton = page.getByRole('button', { name: '登记需求' });

      if (role === 'ROLE_ORGAN_OPERATER' || role === 'ROLE_ORGAN_MANAGER') {
        await expect(deliveryHeading).toBeVisible();
        await expect(supplyHeading).toBeVisible();
        await expect(registerButton).toBeVisible();
      } else if (role === 'ROLE_BUSIAUDIT') {
        await expect(deliveryHeading).toBeVisible();
        await expect(supplyHeading).toBeVisible();
        await expect(registerButton).toHaveCount(0);
      } else {
        await expect(supplyHeading).toHaveCount(0);
        await expect(registerButton).toHaveCount(0);
      }
    }

    for (const role of ALL_ROLES) {
      await setRole(page, role);
      await gotoHash(page, `#/provider/inbox/demand-match/${encodeURIComponent(demandId)}`);
      const detailHeading = page.getByRole('heading', { name: title });
      const provide = page.getByRole('button', { name: '确认提供' });
      const needFix = page.getByRole('button', { name: '驳回补正' });
      const reject = page.getByRole('button', { name: '拒绝提供' });

      if (role === 'ROLE_ORGAN_MANAGER') {
        await expect(detailHeading).toBeVisible();
        await expect(provide).toBeVisible();
        await expect(needFix).toBeVisible();
        await expect(reject).toBeVisible();
      } else {
        await expect(detailHeading).toHaveCount(0);
        await expect(provide).toHaveCount(0);
        await expect(needFix).toHaveCount(0);
        await expect(reject).toHaveCount(0);
      }
    }
  });

  test('异议角色矩阵：5 个岗位的页面与操作权限正确', async ({ page, playwright }) => {
    const api = await playwright.request.newContext();
    const catalogCode = await firstCatalogCode(api);
    test.skip(!catalogCode, 'no catalog row available in DB to anchor objection');

    const tag = Date.now().toString(36);
    let submittedId = '';
    let platformId = '';
    let providerId = '';
    try {
      submittedId = await createSubmittedObjection(api, catalogCode!, `E2E异议待受理矩阵-${tag}`);
      platformId = await createSubmittedObjection(api, catalogCode!, `E2E异议平台确认矩阵-${tag}`);
      await acceptObjection(api, platformId);
      await waitForObjectionStatus(api, platformId, 'platform_investigating');

      providerId = await createSubmittedObjection(api, catalogCode!, `E2E异议部门核查矩阵-${tag}`);
      await acceptObjection(api, providerId);
      await waitForObjectionStatus(api, providerId, 'platform_investigating');
      await returnObjectionForProvider(api, providerId);
      await waitForObjectionStatus(api, providerId, 'provider_investigating');
    } finally {
      await api.dispose();
    }

    for (const role of ALL_ROLES) {
      await setRole(page, role);
      await gotoHash(page, '#/request-flow/objection');
      const deliveryHeading = page.getByRole('heading', { name: '领数据' });
      const inboxHeading = page.getByRole('heading', { name: '我的异议' });
      const createLink = page.getByRole('link', { name: '发起异议' });

      if (role === 'ROLE_ORGAN_OPERATER' || role === 'ROLE_ORGAN_MANAGER') {
        await expect(deliveryHeading).toBeVisible();
        await expect(inboxHeading).toBeVisible();
        await expect(createLink).toBeVisible();
        await gotoHash(page, '#/request-flow/objection/new');
        await expect(page.getByRole('heading', { name: '发起异议' })).toBeVisible();
      } else if (role === 'ROLE_BUSIAUDIT') {
        await expect(deliveryHeading).toBeVisible();
        await expect(inboxHeading).toBeVisible();
        await expect(createLink).toHaveCount(0);
        await gotoHash(page, '#/request-flow/objection/new');
        await expect(page.getByRole('heading', { name: '发起异议' })).toHaveCount(0);
        await expect(page.getByRole('heading', { name: '我的异议' })).toBeVisible();
      } else {
        await expect(inboxHeading).toHaveCount(0);
        await expect(createLink).toHaveCount(0);
      }
    }

    for (const role of ALL_ROLES) {
      await setRole(page, role);
      await gotoHash(page, '#/provider/inbox/objection');
      const inboxHeading = page.getByRole('heading', { name: '异议响应收件箱' });
      if (role === 'ROLE_ORGAN_MANAGER' || role === 'ROLE_BUSIAUDIT') {
        await expect(inboxHeading).toBeVisible();
      } else {
        await expect(inboxHeading).toHaveCount(0);
      }
    }

    await setRole(page, 'ROLE_BUSIAUDIT');
    await gotoHash(page, `#/provider/inbox/objection/${encodeURIComponent(submittedId)}`);
    await expect(page.getByRole('button', { name: '受理' })).toBeVisible();

    await setRole(page, 'ROLE_ORGAN_MANAGER');
    await gotoHash(page, `#/provider/inbox/objection/${encodeURIComponent(submittedId)}`);
    await expect(page.getByRole('button', { name: '受理' })).toHaveCount(0);

    await setRole(page, 'ROLE_ORGAN_MANAGER');
    await gotoHash(page, `#/provider/inbox/objection/${encodeURIComponent(providerId)}`);
    await expect(page.getByRole('button', { name: '提交核查回复' })).toBeVisible();
    await expect(page.getByRole('button', { name: '确认解决' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: '退回核查' })).toHaveCount(0);

    await setRole(page, 'ROLE_BUSIAUDIT');
    await gotoHash(page, `#/provider/inbox/objection/${encodeURIComponent(platformId)}`);
    await expect(page.getByRole('button', { name: '确认解决' })).toBeVisible();
    await expect(page.getByRole('button', { name: '退回核查' })).toBeVisible();
    await expect(page.getByRole('button', { name: '提交核查回复' })).toHaveCount(0);

    for (const role of ['ROLE_ORGAN_OPERATER', 'ROLE_SECURITY_AUDIT', 'ROLE_SYSTEM'] as const) {
      await setRole(page, role);
      await gotoHash(page, `#/provider/inbox/objection/${encodeURIComponent(platformId)}`);
      await expect(page.getByRole('heading', { name: `异议 ${platformId}` })).toHaveCount(0);
      await expect(page.getByRole('button', { name: '受理' })).toHaveCount(0);
      await expect(page.getByRole('button', { name: '提交核查回复' })).toHaveCount(0);
      await expect(page.getByRole('button', { name: '确认解决' })).toHaveCount(0);
    }
  });
});
