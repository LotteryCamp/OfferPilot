import { randomUUID } from 'node:crypto'
import { writeFile } from 'node:fs/promises'
import { expect, test, type Page } from '@playwright/test'
import { z } from 'zod'
import { matterSchema } from '../../src/modules/matters/types'
import { createTestCredentials, registerTestUser } from './auth-user'

const mattersPath = '/api/v1/matters'
const detailBody = z.object({ matter: matterSchema })
const listBody = z.object({ matters: z.array(matterSchema) })

function waitForApi(page: Page, method: string, path: string) {
  return page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === path && response.request().method() === method,
  )
}

test('真实建项后可从列表打开同一事项，刷新后重新读取', async ({ page }, testInfo) => {
  const credentials = createTestCredentials()
  const account = await registerTestUser(page.request, credentials)
  const goal = `联调 ${randomUUID()}`
  const year = 2027

  const [initialList] = await Promise.all([
    waitForApi(page, 'GET', mattersPath),
    page.goto('/matters'),
  ])
  expect(initialList.status()).toBe(200)
  expect(listBody.parse(await initialList.json()).matters).toEqual([])
  await expect(page.getByRole('heading', { name: '还没有事项' })).toBeVisible()

  await page.getByRole('link', { name: '＋ 新建工作区', exact: true }).click()
  await page.getByRole('button', { name: '创建工作区', exact: true }).click()
  await expect(page.getByText('请输入工作区名称', { exact: true })).toBeVisible()
  await expect(page.getByRole('textbox', { name: '工作区名称', exact: true })).toBeFocused()
  await page.getByRole('textbox', { name: '工作区名称', exact: true }).fill(goal)
  await page.getByRole('textbox', { name: '适用年度', exact: true }).fill(String(year))
  const [createdResponse] = await Promise.all([
    waitForApi(page, 'POST', mattersPath),
    page.getByRole('button', { name: '创建工作区', exact: true }).click(),
  ])
  expect(createdResponse.status()).toBe(201)
  const { matter: created } = detailBody.parse(await createdResponse.json())
  expect(created.goal).toBe(goal)
  expect(created.scope_year).toBe(year)
  expect(created.workspace_id).toBe(account.user.workspace_id)

  const overview = `/matters/${created.id}/overview`
  await expect(page).toHaveURL(new RegExp(`${overview}$`))
  await expect(page.getByRole('heading', { name: goal, exact: true })).toBeVisible()

  const [listResponse] = await Promise.all([
    waitForApi(page, 'GET', mattersPath),
    page.getByRole('link', { name: '返回事项工作台', exact: true }).click(),
  ])
  expect(listResponse.status()).toBe(200)
  const { matters } = listBody.parse(await listResponse.json())
  expect(matters.filter((matter) => matter.goal === goal)).toMatchObject([
    { id: created.id, goal, scope_year: year },
  ])

  const detailPath = `${mattersPath}/${created.id}`
  const [detail] = await Promise.all([
    waitForApi(page, 'GET', detailPath),
    page.getByRole('link', { name: new RegExp(`${goal}.*进入工作区`) }).click(),
  ])
  expect(detail.status()).toBe(200)
  expect(detailBody.parse(await detail.json()).matter).toMatchObject({ id: created.id, goal })
  await expect(page).toHaveURL(new RegExp(`${overview}$`))
  await expect(page.getByRole('heading', { name: goal, exact: true })).toBeVisible()

  const [refreshed] = await Promise.all([waitForApi(page, 'GET', detailPath), page.reload()])
  expect(refreshed.status()).toBe(200)
  expect(detailBody.parse(await refreshed.json()).matter).toMatchObject({
    id: created.id,
    goal,
    scope_year: year,
  })
  await expect(page.getByRole('heading', { name: goal, exact: true })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('overview-after-refresh.png'), fullPage: true })
  await page.getByRole('link', { name: '来源与条件', exact: true }).click()
  await expect(page).toHaveURL(new RegExp(`/matters/${created.id}/sources$`))
  await page.reload()
  await expect(page.getByRole('heading', { name: goal, exact: true })).toBeVisible()
  await page.goto('/matters/invalid/overview')
  await expect(page.getByRole('heading', { name: '没有找到这个页面' })).toBeVisible()
  await page.goto('/unknown')
  await expect(page.getByRole('link', { name: '返回我的事项', exact: true })).toBeVisible()

  // 在同一浏览器应用中退出、注册另一账户，再登录原账户，核对列表归属和恢复。
  await page.getByRole('button', { name: '退出登录', exact: true }).click()
  await expect(page.getByRole('heading', { name: '登录', exact: true })).toBeVisible()
  await page.getByRole('link', { name: '注册账号' }).click()
  const nextCredentials = createTestCredentials()
  await page.getByLabel('邮箱', { exact: true }).fill(nextCredentials.email)
  await page.getByLabel('显示名称', { exact: true }).fill(nextCredentials.display_name)
  await page.getByLabel('密码', { exact: true }).fill(nextCredentials.password)
  await page.getByLabel('确认密码', { exact: true }).fill(nextCredentials.password)
  const [nextRegistered, nextList] = await Promise.all([
    waitForApi(page, 'POST', '/api/v1/auth/register'),
    waitForApi(page, 'GET', mattersPath),
    page.getByRole('button', { name: '注册', exact: true }).click(),
  ])
  expect(nextRegistered.status()).toBe(201)
  const nextAccount = await nextRegistered.json()
  expect(nextAccount.user.workspace_id).not.toBe(account.user.workspace_id)
  expect(nextList.status()).toBe(200)
  expect(listBody.parse(await nextList.json()).matters).toEqual([])
  await expect(page.getByRole('heading', { name: '还没有事项', exact: true })).toBeVisible()
  await expect(page.getByText(goal, { exact: true })).toHaveCount(0)
  await page.screenshot({ path: testInfo.outputPath('second-account-empty.png'), fullPage: true })

  await page.getByRole('button', { name: '退出登录', exact: true }).click()
  await expect(page.getByRole('heading', { name: '登录', exact: true })).toBeVisible()
  await page.getByLabel('邮箱', { exact: true }).fill(credentials.email)
  await page.getByLabel('密码', { exact: true }).fill(credentials.password)
  const [returnedLogin, returnedList] = await Promise.all([
    waitForApi(page, 'POST', '/api/v1/auth/login'),
    waitForApi(page, 'GET', mattersPath),
    page.getByRole('button', { name: '登录', exact: true }).click(),
  ])
  expect(returnedLogin.status()).toBe(200)
  expect((await returnedLogin.json()).user.id).toBe(account.user.id)
  expect(returnedList.status()).toBe(200)
  expect(listBody.parse(await returnedList.json()).matters).toMatchObject([
    { id: created.id, goal },
  ])
  await expect(page.getByRole('heading', { name: goal, exact: true })).toBeVisible()
  await page.screenshot({
    path: testInfo.outputPath('original-account-restored.png'),
    fullPage: true,
  })
  await writeFile(
    testInfo.outputPath('matter-round-trip.json'),
    JSON.stringify(
      {
        id: created.id,
        workspaceId: created.workspace_id,
        goal,
        create: createdResponse.status(),
        list: listResponse.status(),
        detail: detail.status(),
        refresh: refreshed.status(),
        secondAccount: nextList.status(),
        originalAccountRestored: returnedList.status(),
      },
      null,
      2,
    ),
    'utf8',
  )
  console.log(`真实复测事项 ${created.id} · ${goal}`)
})
