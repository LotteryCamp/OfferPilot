import { expect, test } from '@playwright/test'

test('未连接服务时可导航与校验，不能创建假事项', async ({ page }, testInfo) => {
  const apiRequests: string[] = []
  page.on('request', (request) => {
    if (new URL(request.url()).pathname.startsWith('/api/')) apiRequests.push(request.url())
  })
  await page.setViewportSize({ width: 1440, height: 960 })
  await page.goto('/matters')
  await expect(page.getByRole('heading', { name: '每一步，都在掌握之中。' })).toBeVisible()
  await expect(
    page.getByRole('navigation', { name: '主导航' }).getByRole('link', { name: '事项工作台' }),
  ).toBeVisible()
  expect(
    await page.locator('.brand-mark').evaluate((image: HTMLImageElement) => image.naturalWidth),
  ).toBe(104)
  await expect(page.getByRole('heading', { name: '暂时无法读取你的事项' })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('01-workbench.png'), fullPage: true })
  await page.getByRole('link', { name: '＋ 新建工作区', exact: true }).click()
  await expect(page.getByRole('heading', { name: '新建工作区', exact: true })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('02-create.png'), fullPage: true })
  await page.getByRole('button', { name: '创建工作区', exact: true }).click()
  await expect(page.getByText('请输入工作区名称', { exact: true })).toBeVisible()
  await expect(page.getByRole('textbox', { name: '工作区名称', exact: true })).toBeFocused()
  await page.screenshot({
    path: testInfo.outputPath('03-create-validation.png'),
    fullPage: true,
    animations: 'disabled',
  })
  await page.getByRole('textbox', { name: '工作区名称', exact: true }).fill('核对本人推免准备范围')
  await page.getByRole('textbox', { name: '适用年度', exact: true }).fill('2027')
  await page.getByRole('button', { name: '创建工作区', exact: true }).click()
  await expect(page.getByRole('alert').filter({ hasText: '当前内容尚未保存' })).toBeVisible()
  await expect(page.locator('.el-form-item.is-error')).toHaveCount(0)
  await expect(page.getByRole('textbox', { name: '工作区名称', exact: true })).toHaveValue(
    '核对本人推免准备范围',
  )
  await expect(page).toHaveURL(/\/matters\/new$/)
  expect(apiRequests).toEqual([])
  await page.screenshot({
    path: testInfo.outputPath('04-create-not-saved.png'),
    fullPage: true,
    animations: 'disabled',
  })
})

test('桌面宽度与窄屏保留主要操作和键盘入口', async ({ page }) => {
  await page.goto('/matters/new')
  for (const width of [1280, 1440, 1920, 640]) {
    await page.setViewportSize({ width, height: 960 })
    await expect(page.getByRole('button', { name: '创建工作区', exact: true })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      width,
    )
  }
  await page.keyboard.press('Tab')
  await page.getByRole('textbox', { name: '工作区名称', exact: true }).focus()
  await expect(page.getByRole('textbox', { name: '工作区名称', exact: true })).toBeFocused()
})

test('深链接保留事项，非法编号和未知页面有恢复入口', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 1135 })
  await page.goto('/matters/00000000-0000-7000-8000-000000000001/overview')
  await expect(page.getByRole('heading', { name: '当前事项尚未读取' })).toBeVisible()
  await page.screenshot({
    path: testInfo.outputPath('05-overview-unconnected.png'),
    fullPage: true,
  })
  await page.getByRole('link', { name: '来源与条件', exact: true }).click()
  await expect(page).toHaveURL(/00000000-0000-7000-8000-000000000001\/sources$/)
  await page.reload()
  await expect(page.getByRole('heading', { name: '当前事项尚未读取' })).toBeVisible()
  await page.goto('/matters/invalid/overview')
  await expect(page.getByRole('heading', { name: '没有找到这个页面' })).toBeVisible()
  await page.goto('/unknown')
  await expect(page.getByRole('link', { name: '返回我的事项', exact: true })).toBeVisible()
})
