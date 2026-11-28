import { randomUUID } from 'node:crypto'
import { expect, test } from '@playwright/test'
import { createTestCredentials, registerTestUser } from './auth-user'

test('真实账户在同一浏览器的标签页之间同步登录和退出状态', async ({ page, context }, testInfo) => {
  const first = createTestCredentials()
  const firstAccount = await registerTestUser(page.request, first)
  const goal = `跨标签页联调 ${randomUUID()}`
  const added = await page.request.post('/api/v1/matters', {
    data: {
      goal,
      type_code: 'pre_recommend',
      scope_year: 2027,
      scope_attrs: {},
    },
  })
  expect(added.status()).toBe(201)
  expect((await added.json()).matter.workspace_id).toBe(firstAccount.user.workspace_id)

  await page.goto('/matters')
  await expect(page.getByRole('heading', { name: goal, exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: first.display_name, exact: true })).toBeVisible()

  const peer = await context.newPage()
  await peer.goto('/account')
  await expect(peer.getByText(first.email, { exact: true })).toBeVisible()
  await peer.getByRole('link', { name: '事项工作台', exact: true }).click()
  await expect(peer.getByRole('heading', { name: goal, exact: true })).toBeVisible()

  const [signedOut] = await Promise.all([
    peer.waitForResponse(
      (response) =>
        new URL(response.url()).pathname === '/api/v1/auth/logout' &&
        response.request().method() === 'POST',
    ),
    peer.getByRole('button', { name: '退出登录', exact: true }).click(),
  ])
  expect(signedOut.status()).toBe(204)
  await expect(peer).toHaveURL(/\/login(?:\?.*)?$/)
  await expect(page).toHaveURL(/\/login(?:\?.*)?$/)
  await expect(page.getByRole('heading', { name: goal, exact: true })).toHaveCount(0)
  await expect(page.getByRole('link', { name: first.display_name, exact: true })).toHaveCount(0)
  await page.screenshot({ path: testInfo.outputPath('peer-tab-signed-out.png'), fullPage: true })

  const second = createTestCredentials()
  await peer.getByRole('link', { name: '注册账号', exact: true }).click()
  await peer.getByLabel('邮箱', { exact: true }).fill(second.email)
  await peer.getByLabel('显示名称', { exact: true }).fill(second.display_name)
  await peer.getByLabel('密码', { exact: true }).fill(second.password)
  await peer.getByLabel('确认密码', { exact: true }).fill(second.password)
  const [registered] = await Promise.all([
    peer.waitForResponse(
      (response) =>
        new URL(response.url()).pathname === '/api/v1/auth/register' &&
        response.request().method() === 'POST',
    ),
    peer.getByRole('button', { name: '注册', exact: true }).click(),
  ])
  expect(registered.status()).toBe(201)
  const secondAccount = await registered.json()
  expect(secondAccount.user.workspace_id).not.toBe(firstAccount.user.workspace_id)
  await expect(peer).toHaveURL(/\/matters$/)
  await expect(page).toHaveURL(/\/matters$/)
  for (const tab of [page, peer]) {
    await expect(tab.getByRole('link', { name: second.display_name, exact: true })).toBeVisible()
    await expect(tab.getByRole('heading', { name: '还没有事项', exact: true })).toBeVisible()
    await expect(tab.getByRole('heading', { name: goal, exact: true })).toHaveCount(0)
  }

  await page.getByRole('link', { name: '个人账户', exact: true }).click()
  await expect(page.getByText(second.email, { exact: true })).toBeVisible()
  await expect(page.getByText(first.email, { exact: true })).toHaveCount(0)
  await page.screenshot({
    path: testInfo.outputPath('peer-tab-current-account.png'),
    fullPage: true,
  })

  await page.getByRole('link', { name: '事项工作台', exact: true }).click()
  await page.getByRole('link', { name: '＋ 新建工作区', exact: true }).click()
  const secondGoal = `同步后的事项 ${randomUUID()}`
  await page.getByRole('textbox', { name: '工作区名称', exact: true }).fill(secondGoal)
  await page.getByRole('textbox', { name: '适用年度', exact: true }).fill('2027')
  const [created] = await Promise.all([
    page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname === '/api/v1/matters' &&
        response.request().method() === 'POST',
    ),
    page.getByRole('button', { name: '创建工作区', exact: true }).click(),
  ])
  expect(created.status()).toBe(201)
  expect((await created.json()).matter.workspace_id).toBe(secondAccount.user.workspace_id)
  await expect(page.getByRole('heading', { name: secondGoal, exact: true })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('peer-tab-new-matter.png'), fullPage: true })
})

test('真实短会话到期后自动隐藏账户和工作区', async ({ page }, testInfo) => {
  test.skip(
    process.env.OFFERPILOT_SHORT_SESSION_TEST !== '1',
    '需要会话有效期不超过 30 秒的独立可写测试后端。',
  )
  const credentials = createTestCredentials()
  const account = await registerTestUser(page.request, credentials)
  const expiresAt = Date.parse(account.session.expires_at)
  expect(expiresAt - Date.now()).toBeGreaterThan(0)
  expect(expiresAt - Date.now()).toBeLessThanOrEqual(30_000)

  await page.goto('/account')
  await expect(page.getByText(credentials.email, { exact: true })).toBeVisible()
  await expect(page).toHaveURL(/\/login(?:\?.*)?$/, {
    timeout: Math.max(expiresAt - Date.now(), 0) + 5_000,
  })
  await expect(page.getByText(credentials.email, { exact: true })).toHaveCount(0)
  await expect(page.getByRole('link', { name: '事项工作台', exact: true })).toHaveCount(0)
  const expired = await page.request.get('/api/v1/auth/me')
  expect(expired.status()).toBe(401)
  expect((await expired.json()).error.code).toBe('authentication_required')
  await page.screenshot({ path: testInfo.outputPath('short-session-expired.png'), fullPage: true })
})
