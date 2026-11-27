import { expect, test, type Page } from '@playwright/test'
import { createTestCredentials } from './auth-user'

const authPath = '/api/v1/auth'

function waitForAuth(page: Page, method: string, action: string) {
  return page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === `${authPath}/${action}` &&
      response.request().method() === method,
  )
}

test('真实注册、会话恢复、退出和登录错误后的恢复', async ({ page }, testInfo) => {
  const credentials = createTestCredentials()

  const [anonymous] = await Promise.all([waitForAuth(page, 'GET', 'me'), page.goto('/matters/new')])
  expect(anonymous.status()).toBe(401)
  expect((await anonymous.json()).error.code).toBe('authentication_required')
  await expect(page).toHaveURL(/\/login(?:\?.*)?$/)
  await expect(page.getByRole('heading', { name: '新建工作区', exact: true })).toHaveCount(0)

  await page.goto('/register')
  await page.getByLabel('邮箱', { exact: true }).fill(credentials.email)
  await page.getByLabel('显示名称', { exact: true }).fill(credentials.display_name)
  await page.getByLabel('密码', { exact: true }).fill(credentials.password)
  await page.getByLabel('确认密码', { exact: true }).fill(credentials.password)

  const [registered] = await Promise.all([
    waitForAuth(page, 'POST', 'register'),
    page.getByRole('button', { name: '注册', exact: true }).click(),
  ])
  expect(registered.status()).toBe(201)
  const account = await registered.json()
  expect(account.user).toMatchObject({
    email: credentials.email,
    display_name: credentials.display_name,
    account_type: 'applicant',
    status: 'active',
  })
  expect(account.session.remember).toBe(false)
  await expect(page).toHaveURL(/\/matters$/)
  await expect(page.getByRole('heading', { name: '还没有事项', exact: true })).toBeVisible()
  const cookies = await page.context().cookies()
  const sessionCookie = cookies.find((cookie) => cookie.name === 'offerpilot_session')
  expect(sessionCookie?.httpOnly).toBe(true)
  expect(sessionCookie?.sameSite).toBe('Lax')

  await page.goto('/account')
  await expect(page.getByRole('heading', { name: '账户信息' })).toBeVisible()
  await expect(page.getByText(credentials.email, { exact: true })).toBeVisible()
  const [restored] = await Promise.all([waitForAuth(page, 'GET', 'me'), page.reload()])
  expect(restored.status()).toBe(200)
  expect((await restored.json()).user).toMatchObject({
    id: account.user.id,
    workspace_id: account.user.workspace_id,
    display_name: credentials.display_name,
  })
  await expect(page.getByText(credentials.email, { exact: true })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('account-restored.png'), fullPage: true })

  const [loggedOut] = await Promise.all([
    waitForAuth(page, 'POST', 'logout'),
    page.getByRole('button', { name: '退出登录', exact: true }).click(),
  ])
  expect(loggedOut.status()).toBe(204)
  await expect(page).toHaveURL(/\/login(?:\?.*)?$/)
  await expect(page.getByText(credentials.display_name, { exact: true })).toHaveCount(0)
  const endedSession = await page.request.get(`${authPath}/me`)
  expect(endedSession.status()).toBe(401)
  expect((await endedSession.json()).error.code).toBe('authentication_required')

  await page.getByRole('link', { name: '注册账号' }).click()
  await page.getByLabel('邮箱', { exact: true }).fill(credentials.email)
  await page.getByLabel('显示名称', { exact: true }).fill(credentials.display_name)
  await page.getByLabel('密码', { exact: true }).fill(credentials.password)
  await page.getByLabel('确认密码', { exact: true }).fill(credentials.password)
  const [duplicate] = await Promise.all([
    waitForAuth(page, 'POST', 'register'),
    page.getByRole('button', { name: '注册', exact: true }).click(),
  ])
  expect(duplicate.status()).toBe(409)
  expect((await duplicate.json()).error.code).toBe('email_already_registered')
  await expect(page.getByTestId('auth-feedback')).toBeVisible()

  await page.goto('/matters/new')
  await expect(page).toHaveURL(/\/login(?:\?.*)?$/)
  await page.getByLabel('邮箱', { exact: true }).fill(credentials.email)
  await page.getByLabel('密码', { exact: true }).fill(`${credentials.password}-wrong`)
  const [invalid] = await Promise.all([
    waitForAuth(page, 'POST', 'login'),
    page.getByRole('button', { name: '登录', exact: true }).click(),
  ])
  expect(invalid.status()).toBe(401)
  expect((await invalid.json()).error.code).toBe('invalid_credentials')
  await expect(page.getByTestId('auth-feedback')).toBeVisible()
  await expect(page.getByLabel('邮箱', { exact: true })).toHaveValue(credentials.email)
  await expect(page).toHaveURL(/\/login(?:\?.*)?$/)
  await page.screenshot({ path: testInfo.outputPath('invalid-credentials.png'), fullPage: true })

  await page.getByLabel('密码', { exact: true }).fill(credentials.password)
  await page.getByRole('checkbox', { name: '记住登录', exact: true }).check()
  const [loggedIn] = await Promise.all([
    waitForAuth(page, 'POST', 'login'),
    page.getByRole('button', { name: '登录', exact: true }).click(),
  ])
  expect(loggedIn.status()).toBe(200)
  const loginAccount = await loggedIn.json()
  expect(loginAccount.user.id).toBe(account.user.id)
  expect(loginAccount.session.remember).toBe(true)
  await expect(page).toHaveURL(/\/matters\/new$/)
  await expect(page.getByRole('heading', { name: '新建工作区', exact: true })).toBeVisible()
  const persistentCookie = (await page.context().cookies()).find(
    (cookie) => cookie.name === 'offerpilot_session',
  )
  expect(persistentCookie?.expires).toBeGreaterThan(0)

  // 撤销当前测试账户会话，验证工作区读取 401 后清理可见身份并恢复登录入口。
  expect((await page.request.post(`${authPath}/logout`)).status()).toBe(204)
  const [expired] = await Promise.all([
    page.waitForResponse(
      (response) =>
        ['/api/v1/auth/me', '/api/v1/matters'].includes(new URL(response.url()).pathname) &&
        response.request().method() === 'GET' &&
        response.status() === 401,
    ),
    page.getByRole('link', { name: '事项工作台', exact: true }).click(),
  ])
  expect((await expired.json()).error.code).toBe('authentication_required')
  await expect(page).toHaveURL(/\/login(?:\?.*)?$/)
  await expect(page.getByText(credentials.display_name, { exact: true })).toHaveCount(0)
  await expect(page.getByRole('heading', { level: 1, name: '每一步，都在掌握之中。' })).toHaveCount(
    0,
  )
  await page.screenshot({ path: testInfo.outputPath('session-ended.png'), fullPage: true })
})
