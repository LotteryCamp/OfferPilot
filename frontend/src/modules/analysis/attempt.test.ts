import { describe, expect, it } from 'vitest'
import {
  analysisRecoveryBlockReason,
  canRecoverAnalysisAttempt,
  createAnalysisAttempt,
  recoverAnalysisAttempt,
} from './attempt'
import { restoreAnalysisAttempt } from './contracts'

const matterId = 'a0000000-0000-4000-8000-000000000001'
const sourceId = 'b0000000-0000-4000-8000-000000000001'
const request = {
  source_urls: ['https://math.fzu.edu.cn/info/1171/10393.htm'],
  publisher: '福州大学数学与统计学院',
  scope_year: 2027,
  scope: '2027 届、本院、校内推免推荐',
}

describe('分析请求的创建与恢复', () => {
  it('新分析生成独立操作编号，保存公开来源参数的副本', () => {
    const input = { ...request, source_urls: [...request.source_urls] }
    const first = createAnalysisAttempt(matterId, sourceId, input)
    const second = createAnalysisAttempt(matterId, sourceId, input)
    expect(first.operationId).not.toBe(second.operationId)
    expect(first.request).toEqual(request)
    input.source_urls[0] = 'https://example.edu/another-notice'
    expect(first.request.source_urls).toEqual(request.source_urls)
    expect(first).toMatchObject({ matterId, sourceId, runId: null, status: null })
  })

  it('刷新后沿用原操作编号与原参数', () => {
    const original = createAnalysisAttempt(matterId, sourceId, request)
    const restored = restoreAnalysisAttempt(JSON.stringify(original), matterId)
    expect(canRecoverAnalysisAttempt(restored)).toBe(true)
    expect(recoverAnalysisAttempt(restored, matterId, sourceId, request.scope_year)).toEqual(
      original,
    )
    expect(createAnalysisAttempt(matterId, sourceId, request).operationId).not.toBe(
      original.operationId,
    )
  })

  it('拒绝恢复到其他事项或来源，保留原记录', () => {
    const original = createAnalysisAttempt(matterId, sourceId, request)
    const stored = JSON.stringify(original)
    expect(() =>
      recoverAnalysisAttempt(original, crypto.randomUUID(), sourceId, request.scope_year),
    ).toThrow('上次分析所属的事项')
    expect(() =>
      recoverAnalysisAttempt(original, matterId, crypto.randomUUID(), request.scope_year),
    ).toThrow('原来源')
    expect(JSON.stringify(original)).toBe(stored)
  })

  it('恢复按钮要求原事项、原来源和相同的适用年度', () => {
    const original = createAnalysisAttempt(matterId, sourceId, request)
    expect(analysisRecoveryBlockReason(original, matterId, sourceId, 2027)).toBe('')
    expect(analysisRecoveryBlockReason(original, matterId, null, 2027)).toContain('原来源')
    expect(analysisRecoveryBlockReason(original, matterId, sourceId, 2028)).toContain('年度已变化')
    expect(analysisRecoveryBlockReason(original, matterId, sourceId, null)).toContain('年度已变化')
    expect(() => recoverAnalysisAttempt(original, matterId, sourceId, 2028)).toThrow('年度已变化')
    expect(analysisRecoveryBlockReason(null, matterId, sourceId, 2027)).toContain('核对已保存结果')
  })

  it.each(['运行中', '等待确认', '等待用户', '已完成', '失败', '已取消', '已中断', '未发起'])(
    '状态已知为 %s 时交由查询或新的分析处理',
    (status) => {
      const attempt = { ...createAnalysisAttempt(matterId, sourceId, request), status }
      expect(canRecoverAnalysisAttempt(attempt)).toBe(false)
      expect(() => recoverAnalysisAttempt(attempt, matterId, sourceId, request.scope_year)).toThrow(
        '明确状态',
      )
    },
  )

  it('已取得运行编号时使用状态查询', () => {
    const attempt = {
      ...createAnalysisAttempt(matterId, sourceId, request),
      runId: 'run-6f1c0e37c2ab',
    }
    expect(canRecoverAnalysisAttempt(attempt)).toBe(false)
    expect(() => recoverAnalysisAttempt(attempt, matterId, sourceId, request.scope_year)).toThrow(
      '明确状态',
    )
  })

  it('兼容缺少请求参数的旧记录，要求先核对已保存结果', () => {
    const original = createAnalysisAttempt(matterId, sourceId, request)
    const legacy = {
      matterId,
      sourceId,
      operationId: original.operationId,
      runId: null,
      status: null,
    }
    const restored = restoreAnalysisAttempt(JSON.stringify(legacy), matterId)
    expect(restored).toEqual(legacy)
    expect(canRecoverAnalysisAttempt(restored)).toBe(false)
    expect(canRecoverAnalysisAttempt(null)).toBe(false)
    expect(() => recoverAnalysisAttempt(restored, matterId, sourceId, request.scope_year)).toThrow(
      '缺少恢复参数',
    )
  })

  it.each([
    'javascript:alert(1)',
    'https://user:pass@example.edu/notice',
    'https://:pass@example.edu/notice',
    'not a URL',
  ])('不保存或恢复无效来源链接 %s', (url) => {
    const invalid = { ...request, source_urls: [url] }
    expect(() => createAnalysisAttempt(matterId, sourceId, invalid)).toThrow()
    const attempt = { ...createAnalysisAttempt(matterId, sourceId, request), request: invalid }
    expect(() => restoreAnalysisAttempt(JSON.stringify(attempt), matterId)).toThrow()
  })

  it('个人事实和正文不能混入恢复参数', () => {
    for (const extra of [{ confirmed_facts: { 'gpa.rank': 10 } }, { text: '个人材料正文' }]) {
      expect(() => createAnalysisAttempt(matterId, sourceId, { ...request, ...extra })).toThrow()
    }
  })
})
