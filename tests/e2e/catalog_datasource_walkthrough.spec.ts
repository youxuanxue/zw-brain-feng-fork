import { test, expect } from '@playwright/test';
import { E2E_BASE_URL, gotoHash, setRole, skipUnlessBackend, waitAppReady } from './helpers';

const UNIQUE = `e2e-${Date.now()}`;

async function submitModal(page: import('@playwright/test').Page) {
  await page.locator('form.modal').evaluate((form) => (form as HTMLFormElement).requestSubmit());
}

test.describe('catalog datasource E2E walkthrough', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await skipUnlessBackend(page, testInfo);
    await page.goto(E2E_BASE_URL);
    await waitAppReady(page);
  });

  test('A: provider home header and role pills', async ({ page }) => {
    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, '#/provider');
    await expect(page.getByRole('heading', { name: '提供方管理' })).toBeVisible();
    await expect(page.locator('body')).toContainText('先登记数据源，再编目或挂接');
    const links = page.locator('.focus-link-pill');
    const texts = (await links.allTextContents()).map((t) => t.trim());
    const dsIdx = texts.findIndex((t) => t.includes('数据源管理'));
    const inlineIdx = texts.findIndex((t) => t.includes('在线编制目录'));
    expect(dsIdx).toBeGreaterThanOrEqual(0);
    expect(inlineIdx).toBeGreaterThanOrEqual(0);
    expect(dsIdx).toBeLessThan(inlineIdx);

    await setRole(page, 'ROLE_ORGAN_MANAGER');
    await gotoHash(page, '#/provider');
    await expect(page.getByRole('heading', { name: '提供方管理' })).toBeVisible();
  });

  test('B: datasource manage CRUD and copy gate', async ({ page }) => {
    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, '#/provider/datasources');
    await expect(page.getByRole('heading', { name: '数据源管理' })).toBeVisible();
    await expect(page.locator('body')).not.toContainText(/endpoint|元数据|导入示例数据/i);

    await page.getByRole('button', { name: /前置库/ }).click();
    await expect(page.getByRole('button', { name: /前置库/ })).toBeVisible();

    await page.getByTestId('datasource-add').click();
    await page.getByLabel('显示名称').fill(`验收数据源-${UNIQUE}`);
    await page.getByLabel('库实例名').fill(`db_${UNIQUE}`);
    await submitModal(page);
    await expect(page.locator('body')).toContainText('数据源已登记');
    await expect(page.getByTestId('datasource-table')).toContainText(`验收数据源-${UNIQUE}`);
    const row = page.locator('tr', { hasText: `验收数据源-${UNIQUE}` });
    await expect(row.locator('.status-tag')).toContainText('未探测');
    await row.getByRole('button', { name: '检查连通' }).click();
    await expect(page.locator('body')).toContainText(/同步记录|未探测|连通/);

    await row.getByRole('button', { name: '编辑' }).click();
    await page.getByLabel('联系人').fill('张三');
    await submitModal(page);
    await expect(page.locator('body')).toContainText('数据源已更新');

    await page.getByPlaceholder('名称 / 库实例 / 部门').fill(`验收数据源-${UNIQUE}`);
    await expect(page.getByTestId('datasource-table')).toContainText(`验收数据源-${UNIQUE}`);

    page.once('dialog', (d) => d.accept());
    await row.getByRole('button', { name: '删除' }).click();
    await expect(page.locator('body')).toContainText('数据源已删除');
    await expect(page.getByTestId('datasource-table')).not.toContainText(`验收数据源-${UNIQUE}`);
  });

  test('B7: business auditor blocked from datasource page', async ({ page }) => {
    await setRole(page, 'ROLE_BUSIAUDIT');
    await gotoHash(page, '#/provider/datasources');
    await page.waitForTimeout(800);
    expect(page.url()).not.toMatch(/datasources/);
  });

  test('C: reverse catalog operator vs manager flow', async ({ page }) => {
    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, '#/provider/wizard/reverse-catalog');
    await expect(page.getByRole('heading', { name: '反向编目' })).toBeVisible();
    const dsSelect = page.getByTestId('reverse-datasource-select');
    await expect(dsSelect.locator('option')).not.toHaveCount(1);

    await dsSelect.selectOption({ index: 1 });
    await page.getByRole('button', { name: '下一步' }).click();
    await expect(page.locator('body')).toContainText(/正在加载库表|表名称|还没有可用表/);

    const chooseBtn = page.getByRole('button', { name: '选择' }).first();
    if (await chooseBtn.isVisible().catch(() => false)) {
      await chooseBtn.click();
      await expect(page.locator('body')).toContainText('确认并创建草稿');
      const createBtn = page.getByTestId('reverse-catalog-create');
      if (!(await createBtn.isEnabled())) {
        await expect(createBtn).toBeDisabled();
      } else {
        await createBtn.click();
        await page.waitForTimeout(1200);
        expect(page.url()).toMatch(/#\/provider$/);
        expect(page.url()).not.toMatch(/field-decision/);
      }
    }

    await setRole(page, 'ROLE_ORGAN_MANAGER');
    await gotoHash(page, '#/provider/wizard/reverse-catalog');
    await page.getByTestId('reverse-datasource-select').selectOption({ index: 1 });
    await page.getByRole('button', { name: '下一步' }).click();
    const mgrChoose = page.getByRole('button', { name: '选择' }).first();
    if (await mgrChoose.isVisible().catch(() => false)) {
      await mgrChoose.click();
      const createBtn = page.getByTestId('reverse-catalog-create');
      if (await createBtn.isEnabled()) {
        await createBtn.click();
        await page.waitForTimeout(1200);
        expect(page.url()).toMatch(/field-decision/);
      }
    }
  });

  test('D: hookup wizard datasource select', async ({ page }) => {
    await setRole(page, 'ROLE_ORGAN_OPERATER');
    await gotoHash(page, '#/provider/wizard/hookup-submit');
    await expect(page.getByRole('heading', { name: '资源挂接' })).toBeVisible();
    const dsSelect = page.getByTestId('hookup-datasource-select');
    await expect(dsSelect).toBeVisible();
    const optCount = await dsSelect.locator('option').count();
    if (optCount <= 1) {
      await expect(page.locator('body')).toContainText('数据源管理');
    } else {
      await dsSelect.selectOption({ index: 1 });
      await dsSelect.selectOption({ index: 0 });
      await expect(dsSelect).toHaveValue('');
    }
  });
});
