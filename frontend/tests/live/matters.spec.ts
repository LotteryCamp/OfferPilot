import { randomUUID } from 'node:crypto'
import { writeFile } from 'node:fs/promises'
import { expect, test, type Page } from '@playwright/test'
import { z } from 'zod'
import { matterSchema } from '../../src/modules/matters/types'

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
  const goal = `Alpha 联调 ${randomUUID()}`
  const year = 2027

  const [initialList] = await Promise.all([
    waitForApi(page, 'GET', mattersPath),
    page.goto('/matters'),
  ])
  expect(initialList.status()).toBe(200)
  listBody.parse(await initialList.json())

  await page.getByRole('link', { name: '＋ 新建工作区', exact: true }).click()
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
  await writeFile(
    testInfo.outputPath('matter-round-trip.json'),
    JSON.stringify(
      {
        id: created.id,
        goal,
        create: createdResponse.status(),
        list: listResponse.status(),
        detail: detail.status(),
        refresh: refreshed.status(),
      },
      null,
      2,
    ),
    'utf8',
  )
  console.log(`真实复测事项 ${created.id} · ${goal}`)
})
