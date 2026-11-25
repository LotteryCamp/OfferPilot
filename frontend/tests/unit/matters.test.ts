import { describe, expect, it } from 'vitest'
import {
  createMatterSchema,
  matterSchema,
  matterStatusLabels,
  matterYearLabel,
  planStatusLabels,
} from '../../src/modules/matters/types'
import { describeFailure } from '../../src/modules/matters/errors'
import { isMatterId, matterPath } from '../../src/router/paths'

describe('事项表单校验', () => {
  const input = {
    goal: '核对本人推免准备范围',
    type_code: 'pre_recommend',
    scope_year: 2027,
    scope_attrs: {},
  }
  it('去除目标首尾空白，保留实际年度', () => {
    expect(createMatterSchema.parse({ ...input, goal: ' 核对本人推免准备范围 ' })).toEqual(input)
  })
  it.each(['', '   ', '目标'.repeat(101)])('拒绝不符合契约的目标 %j', (goal) => {
    expect(createMatterSchema.safeParse({ ...input, goal }).success).toBe(false)
  })
  it.each([Number.NaN, 2019, 2101, 2026.5])('拒绝无效年度 %s', (scope_year) => {
    expect(createMatterSchema.safeParse({ ...input, scope_year }).success).toBe(false)
  })
  it('只允许当前推免类型', () => {
    expect(createMatterSchema.safeParse({ ...input, type_code: 'competition' }).success).toBe(false)
  })

  it('可读取旧事项的未填写年度及范围，新建仍要求有效年度', () => {
    expect(matterYearLabel(matterSchema.shape.scope_year.parse(null))).toBe('适用年度未填写')
    expect(matterSchema.shape.scope_attrs.parse(null)).toBeNull()
    expect(createMatterSchema.safeParse({ ...input, scope_year: null }).success).toBe(false)
  })
})

describe('事项路由与状态语义', () => {
  const id = '00000000-0000-7000-8000-000000000001'
  it.each(['', '../matters', '42', ['id'], undefined])('拒绝无效事项编号 %j', (value) => {
    expect(isMatterId(value)).toBe(false)
  })
  it('保持同一事项编号并约束页面范围', () => {
    expect(matterPath(id, 'sources')).toBe(`/matters/${id}/sources`)
    expect(() => matterPath(id, '../../other')).toThrow()
  })
  it('将合法大写UUID统一为后端标准小写', () => {
    const uuid = 'A0000000-0000-4000-8000-000000000001'
    expect(matterPath(uuid)).toBe(`/matters/${uuid.toLowerCase()}/overview`)
  })
  it('区分事项进度与候选决定', () => {
    expect(matterStatusLabels.draft).toBe('草稿')
    expect(planStatusLabels.pending).toBe('待本人审阅')
    expect(planStatusLabels.confirmed).toBe('已确认')
  })
})

describe('失败后的写入安全', () => {
  it('HTTP 408 后创建结果不确定，应先检查列表', () => {
    const failure = describeFailure({ response: { status: 408 } }, true)
    expect(failure.uncertain).toBe(true)
    expect(failure.message).toContain('重新读取事项列表')
    expect(describeFailure({ response: { status: 408 } }).uncertain).toBe(false)
  })

  it('未知状态的错误提示不包含后端错误正文', () => {
    const error = {
      response: {
        status: 418,
        data: { error: { code: 'internal_error', message: '后端内部诊断详情' } },
      },
    }
    expect(describeFailure(error).message).toBe('暂时无法读取事项，请检查服务连接后重试。')
    expect(describeFailure(error, true).message).toBe(
      '暂时无法创建工作区，请检查提交信息和服务连接后重试。',
    )
  })

  it('缺少已发布模板时给出明确的处理提示', () => {
    const failure = describeFailure(
      {
        response: {
          status: 409,
          data: { error: { code: 'template_version_missing', message: '缺少已发布模板' } },
        },
      },
      true,
    )
    expect(failure).toEqual({
      message: '此事项类型尚无已发布模板。请联系管理员补齐后重试。',
      uncertain: false,
    })
  })

  it('无法确认写入结果时阻止直接重试', () => {
    expect(describeFailure(new Error('connection lost'), true).uncertain).toBe(true)
  })
  it('读取失败允许重读且不报告写入成功', () => {
    const failure = describeFailure(new Error('connection lost'))
    expect(failure.uncertain).toBe(false)
    expect(failure.message).toContain('无法读取')
  })
})
