import { createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { describe, expect, it } from 'vitest'
import RequirementList from './RequirementList.vue'
import type { Snapshot } from './contracts'

const sourceId = 'b0000000-0000-4000-8000-000000000001'
const snapshotId = 'b0000000-0000-4000-8000-000000000002'
const snapshotKey = `${sourceId}/${snapshotId}`
type Requirement = Snapshot['requirements'][number]

function requirement(overrides: Partial<Requirement> = {}): Requirement {
  return {
    id: 'b0000000-0000-4000-8000-000000000003',
    matter_id: 'a0000000-0000-4000-8000-000000000001',
    snapshot_id: snapshotId,
    field_key: 'gpa.rank',
    label: '成绩排名',
    obligation_nature: 'required',
    extract_status: 'checked',
    scope: '2027 届本科生',
    value_text: '成绩排名前 20%',
    value_type: 'text',
    confidence: null,
    checked_at: null,
    evidence: [],
    self_check: null,
    ...overrides,
  }
}

function render(requirements: Requirement[], availableSnapshots = new Set<string>()) {
  const snapshot: Snapshot = {
    id: snapshotId,
    source_id: sourceId,
    version_no: 1,
    content_hash: 'a'.repeat(64),
    title: '推免申请通知',
    published_date: null,
    text: null,
    fragments: [],
    fetched_at: null,
    is_current: true,
    requirements,
  }
  return renderToString(createSSRApp(RequirementList, { snapshot, availableSnapshots }))
}

describe('条件列表的自查展示', () => {
  it('空快照提示等待分析，保留当前快照标识', async () => {
    const html = await render([])
    expect(html).toContain(`data-snapshot-id="${snapshotId}"`)
    expect(html).toContain('已读取，待分析')
    expect(html).toContain('此快照尚无关联要求，可先查看原文。')
    expect(html).not.toContain('data-testid="requirement-card"')
  })

  it.each([
    ['matched', '按现有信息符合'],
    ['not_matched', '按现有信息不符合'],
    ['missing_info', '待补充信息'],
    ['needs_user_review', '待用户核对'],
  ])('显示 %s 的结论、原因及要求性质', async (conclusion, label) => {
    const html = await render([
      requirement({
        self_check: {
          conclusion,
          reason: '按本人当前事项的排名信息核对',
          missing_fields: [],
          computed_deadline_at: null,
          gaps: [],
        },
      }),
    ])
    expect(html).toContain(`data-conclusion="${conclusion}"`)
    expect(html).toContain(label)
    expect(html).toContain('按本人当前事项的排名信息核对')
    expect(html).toContain('必需')
    expect(html).toContain('已执行检查')
    expect(html).not.toContain('待补充信息项：')
    expect(html).not.toContain('按规则计算的截止时间：')
  })

  it.each([null, undefined])('没有自查结果时展示待核对说明', async (self_check) => {
    const html = await render([requirement({ self_check, extract_status: 'to_review' })])
    expect(html).toContain('待核对')
    expect(html).toContain('尚无可读取的个人自查结果，请先核对下方来源依据。')
    expect(html).not.toContain('data-testid="self-check"')
    expect(html).not.toContain('按现有信息符合')
  })

  it('显示缺项、缺口定位及北京时间，并提供已返回快照的入口', async () => {
    const html = await render(
      [
        requirement({
          self_check: {
            conclusion: 'missing_info',
            reason: '缺少本人排名信息',
            missing_fields: ['gpa.rank'],
            computed_deadline_at: '2026-09-10T07:00:00Z',
            gaps: [
              {
                gap_type: 'missing_personal_fact',
                description: '请补充本人排名和参与排名总人数',
                locator: '申请条件第2项',
                source_id: sourceId,
                snapshot_id: snapshotId,
              },
            ],
          },
        }),
      ],
      new Set([snapshotKey]),
    )
    expect(html).toContain('待补充信息项：gpa.rank')
    expect(html).toContain('请补充本人排名和参与排名总人数')
    expect(html).toContain('原文位置：申请条件第2项')
    expect(html).toContain('15:00（北京时间）')
    expect(html).toContain('查看缺口对应快照')
  })

  it('未返回缺口对应快照时保留缺口说明', async () => {
    const html = await render([
      requirement({
        self_check: {
          conclusion: 'needs_user_review',
          reason: '请核对适用范围',
          missing_fields: [],
          computed_deadline_at: null,
          gaps: [
            {
              gap_type: 'scope_uncertain',
              description: '请核对本人是否属于通知适用范围',
              locator: null,
              source_id: sourceId,
              snapshot_id: snapshotId,
            },
          ],
        },
      }),
    ])
    expect(html).toContain('请核对本人是否属于通知适用范围')
    expect(html).not.toContain('查看缺口对应快照')
    expect(html).not.toContain('原文位置：')
  })

  it.each([true, false])('根据出处快照是否可用显示入口或核对提示：%s', async (available) => {
    const html = await render(
      [
        requirement({
          checked_at: '2026-09-10T07:00:00Z',
          evidence: [
            {
              id: 'b0000000-0000-4000-8000-000000000004',
              source_id: sourceId,
              snapshot_id: snapshotId,
              locator_kind: 'section',
              locator: '申请条件第2项',
              quote: '成绩排名位于前 20%',
              quote_hash: null,
              fetched_at: null,
            },
          ],
        }),
      ],
      available ? new Set([snapshotKey]) : new Set(),
    )
    expect(html).toContain('原文位置 · 申请条件第2项')
    expect(html).toContain('成绩排名位于前 20%')
    expect(html).toContain('适用范围：2027 届本科生')
    expect(html).toContain('检查时间：')
    expect(html).toContain(`来源 ${sourceId} / 快照 ${snapshotId}`)
    expect(html.includes('查看该出处快照')).toBe(available)
    expect(html.includes('本列表未返回该出处快照，请按标识核对。')).toBe(!available)
  })

  it('缺少要求内容、范围和出处时明确提示补充', async () => {
    const html = await render([requirement({ value_text: null, scope: null })])
    expect(html).toContain('要求内容待补充')
    expect(html).toContain('未提供，需核对')
    expect(html).toContain('尚未提供出处定位，需补充后核对。')
  })

  it('原文中的 HTML 作为文字显示', async () => {
    const html = await render([
      requirement({ value_text: '<script>alert(1)</script>', label: '<img src=x>' }),
    ])
    expect(html).toContain('&lt;script&gt;alert(1)&lt;/script&gt;')
    expect(html).toContain('&lt;img src=x&gt;')
    expect(html).not.toContain('<script>')
    expect(html).not.toContain('<img src=x>')
  })
})
