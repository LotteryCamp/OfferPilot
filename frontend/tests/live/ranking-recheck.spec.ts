import { randomUUID } from 'node:crypto'
import { expect, test } from '@playwright/test'
import { registerTestUser } from './auth-user'

const matters = '/api/v1/matters'
const consentPath = '/api/v1/model-transfer-consent'
const notice = 'https://math.fzu.edu.cn/info/1171/10393.htm'

test.skip(
  process.env.OFFERPILOT_RANKING_RECHECK_TEST !== '1',
  '需要独立可写数据库、真实公开来源及未配置外部模型密钥的测试后端。',
)

for (const pageKind of ['workspace', 'stale-save-prop'] as const) {
  test(`保存并重新自查提交真实 Agent 请求（${pageKind}）`, async ({ page }) => {
    const request = page.request
    await registerTestUser(request)
    const created = await request.post(matters, {
      data: {
        goal: `QA 福州大学 2027 届公开推免通知 ${randomUUID()}`,
        type_code: 'pre_recommend',
        scope_year: 2027,
        scope_attrs: { school: '福州大学' },
      },
    })
    expect(created.status()).toBe(201)
    const { matter } = await created.json()
    const context = `${matters}/${matter.id}`
    const imported = await request.post(`${context}/sources/read`, {
      data: {
        url: notice,
        publisher: '福州大学数学与统计学院',
        scope: '2027 届、本院、校内推免推荐',
        scope_year: 2027,
      },
    })
    expect(imported.status()).toBe(201)
    const consent = await request.post(consentPath)
    expect(consent.status()).toBe(200)

    await page.goto(
      pageKind === 'workspace'
        ? `/matters/${matter.id}/sources`
        : `/tests/live/fixtures/ranking-recheck.html?matter=${encodeURIComponent(matter.id)}`,
    )
    await expect(page.getByTestId('consent-active')).toBeVisible()
    const manual = page.getByTestId('analysis-start')
    if (pageKind === 'stale-save-prop') await expect(manual).toBeDisabled()
    else await expect(manual).toBeEnabled()
    await page.locator('#ranking-rankPosition').fill('18')
    await page.locator('#ranking-totalStudents').fill('120')
    await page.getByText('我已核对这两项信息采用同一统计范围，并确认填写内容真实。').click()

    const factPath = `${context}/facts/gpa.rank`
    const runPath = `${context}/agent-runs`
    const factSaved = page.waitForResponse(
      (response) =>
        response.request().method() === 'PUT' && new URL(response.url()).pathname === factPath,
    )
    const run = page.waitForResponse(
      (response) =>
        response.request().method() === 'POST' && new URL(response.url()).pathname === runPath,
    )
    const [saved, analysed] = await Promise.all([
      factSaved,
      run,
      page.getByTestId('ranking-save').click(),
    ])
    expect(saved.status()).toBe(200)
    const { fact } = await saved.json()
    expect(fact).toMatchObject({ matter_id: matter.id, version_no: 1 })
    await expect(page.getByTestId('ranking-saved')).toHaveAttribute('data-fact-id', fact.id)
    expect(analysed.status()).toBe(200)
    const requestBody = analysed.request().postDataJSON()
    expect(requestBody.source_urls).toEqual([notice])
    expect(requestBody).not.toHaveProperty('confirmed_facts')
    expect(requestBody).not.toHaveProperty('model_transfer_consent_id')
    const result = (await analysed.json()).run
    expect(result).toMatchObject({
      status: '失败',
      persisted_plan_id: null,
      written_tasks: [],
      error: { code: 'MODEL_ERROR' },
    })
    await expect(page.getByTestId('analysis-result')).toHaveAttribute('data-run-id', result.run_id)
    if (pageKind === 'stale-save-prop') await expect(manual).toBeDisabled()
    await page.getByTestId('analysis-panel').getByRole('link', { name: '查看候选计划 →' }).click()
    await expect(page).toHaveURL(new RegExp(`/matters/${matter.id}/plan$`))
    await expect(page.getByTestId('plan-page')).toBeVisible()
    await expect(page.getByText('当前事项暂无候选计划', { exact: true })).toBeVisible()
  })
}
