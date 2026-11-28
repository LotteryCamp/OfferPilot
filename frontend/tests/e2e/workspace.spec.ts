import { expect, test } from '@playwright/test'

test('认证服务未连接时保护工作区并提供会话重试', async ({ page }, testInfo) => {
  const apiRequests: string[] = []
  page.on('request', (request) => {
    const path = new URL(request.url()).pathname
    if (path.startsWith('/api/')) apiRequests.push(path)
  })
  await page.setViewportSize({ width: 1440, height: 960 })
  await page.goto('/matters')
  await expect(page.getByRole('heading', { name: '暂时无法确认登录状态' })).toBeVisible()
  await expect(page.getByRole('link', { name: '前往登录' })).toBeVisible()
  await expect(page.getByRole('heading', { level: 1, name: '每一步，都在掌握之中。' })).toHaveCount(
    0,
  )
  await expect(page.getByRole('link', { name: '＋ 新建工作区', exact: true })).toHaveCount(0)
  expect(apiRequests).toContain('/api/v1/auth/me')
  expect(apiRequests.some((path) => path.startsWith('/api/v1/matters'))).toBe(false)
  await page.screenshot({ path: testInfo.outputPath('session-unavailable.png'), fullPage: true })
  await page.getByRole('link', { name: '前往登录' }).click()
  await expect(page.getByRole('button', { name: '重新检查会话' })).toBeVisible()
  const [retried] = await Promise.all([
    page.waitForRequest((request) => new URL(request.url()).pathname === '/api/v1/auth/me'),
    page.getByRole('button', { name: '重新检查会话' }).click(),
  ])
  expect(retried.method()).toBe('GET')
  await expect(page.getByRole('button', { name: '重新检查会话' })).toBeVisible()
  expect(apiRequests.some((path) => path.startsWith('/api/v1/matters'))).toBe(false)
})

test('桌面与窄屏的登录入口及键盘操作', async ({ page }, testInfo) => {
  await page.goto('/login')
  await expect(page.getByRole('heading', { name: '登录', exact: true })).toBeVisible()
  const email = page.getByLabel('邮箱', { exact: true })
  const password = page.getByLabel('密码', { exact: true })
  for (const width of [1280, 1440, 1920, 640, 375]) {
    await page.setViewportSize({ width, height: 960 })
    await expect(email).toBeVisible()
    await expect(password).toBeVisible()
    await expect(page.getByRole('button', { name: '登录', exact: true })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      width,
    )
  }
  for (let step = 0; step < 24; step++) {
    await page.keyboard.press('Tab')
    if (await email.evaluate((field) => document.activeElement === field)) break
  }
  await expect(email).toBeFocused()
  await page.screenshot({ path: testInfo.outputPath('login-narrow.png'), fullPage: true })
})

test('登录与注册公开入口可以往返，保护事项深链接', async ({ page }, testInfo) => {
  const businessRequests: string[] = []
  page.on('request', (request) => {
    const path = new URL(request.url()).pathname
    if (path.startsWith('/api/v1/matters')) businessRequests.push(path)
  })
  await page.goto('/login')
  await page.getByRole('link', { name: '注册账号' }).click()
  await expect(page.getByRole('heading', { name: '注册', exact: true })).toBeVisible()
  await expect(page.getByLabel('显示名称', { exact: true })).toBeVisible()
  await expect(page.getByLabel('确认密码', { exact: true })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('registration.png'), fullPage: true })
  await page.getByRole('link', { name: '返回登录' }).click()
  await expect(page.getByRole('heading', { name: '登录', exact: true })).toBeVisible()
  await page.goto('/matters/00000000-0000-7000-8000-000000000001/overview')
  await expect(page.getByRole('heading', { name: '暂时无法确认登录状态' })).toBeVisible()
  await expect(page.getByRole('navigation', { name: '当前事项页面' })).toHaveCount(0)
  expect(businessRequests).toEqual([])
})
