import { AxiosError, AxiosHeaders } from 'axios'
import { describe, expect, it } from 'vitest'
import { analysisError, analysisInput, isConsentRejectedStart, isMissingRun } from './api'
import { runResponse } from './contracts'

function failure(status: number, code: string) {
  return new AxiosError<{ error: { code?: string; message?: string; next?: string } }>(
    '请求被拒绝',
    'ERR_BAD_REQUEST',
    undefined,
    undefined,
    {
      status,
      statusText: '',
      headers: {},
      config: { headers: new AxiosHeaders() },
      data: { error: { code } },
    },
  )
}

describe('分析启动的授权拒绝', () => {
  it.each(['ECONNABORTED', 'ETIMEDOUT'])('前端等待超时 %s 提示读取已保存结果', (code) => {
    const message = analysisError(new AxiosError('timeout', code))
    expect(message).toContain('前端时限')
    expect(message).toContain('后端可能仍在执行')
    expect(message).toContain('刷新已保存结果')
  })
  it.each([502, 504])('HTTP %s 提示从持久化结果核对分析', (status) => {
    const error = failure(status, 'gateway_error')
    expect(isConsentRejectedStart(error)).toBe(false)
    expect(analysisError(error)).toContain('后端可能仍在执行')
    expect(analysisError(error)).toContain('刷新已保存结果')
  })
  it('运行只发送分析字段，由后端查询全局授权', () => {
    const input = {
      source_urls: ['https://example.edu/notice'],
      publisher: '官方发布方',
      scope_year: 2027,
      operation_id: crypto.randomUUID(),
    }
    expect(analysisInput.parse(input)).toEqual(input)
    expect(
      analysisInput.safeParse({ ...input, model_transfer_consent_id: crypto.randomUUID() }).success,
    ).toBe(false)
  })
  it.each(['model_transfer_consent_required', 'model_transfer_consent_invalid'])(
    '%s 的422响应表示尚未创建运行',
    (code) => {
      expect(isConsentRejectedStart(failure(422, code))).toBe(true)
    },
  )
  it.each([408, 429, 500])('HTTP %s 不能归为确定未创建', (status) => {
    expect(isConsentRejectedStart(failure(status, 'model_transfer_consent_invalid'))).toBe(false)
  })
  it('连接中断与其他业务错误继续保留原有处理', () => {
    expect(isConsentRejectedStart(new AxiosError('连接中断'))).toBe(false)
    expect(isConsentRejectedStart(failure(422, 'other_error'))).toBe(false)
    expect(isConsentRejectedStart(new Error('响应校验失败'))).toBe(false)
  })
})

describe('恢复分析时的错误提示与查询边界', () => {
  it('只将明确的运行不存在响应归为不可查询', () => {
    expect(isMissingRun(failure(404, 'agent_run_not_found'))).toBe(true)
    expect(isMissingRun(failure(404, 'matter_not_found'))).toBe(false)
    expect(isMissingRun(failure(503, 'agent_run_not_found'))).toBe(false)
    expect(isMissingRun(new AxiosError('连接中断'))).toBe(false)
    expect(isMissingRun(new Error('响应无法核验'))).toBe(false)
  })

  it('展示明确拒绝的原因及恢复建议', () => {
    const error = failure(422, 'scope_year_mismatch')
    error.response!.data = {
      error: { message: '适用年度与事项不一致', next: '核对当前事项的年度' },
    }
    expect(analysisError(error)).toBe('适用年度与事项不一致；核对当前事项的年度')
    error.response!.data = { error: { message: '请重新登录' } }
    expect(analysisError(error)).toBe('请重新登录')
  })

  it('服务异常或错误正文不完整时保持结果待确认', () => {
    const unavailable = failure(503, 'internal_error')
    unavailable.response!.data = { error: { message: '服务端内部诊断内容' } }
    expect(analysisError(unavailable)).toContain('运行结果暂无法确认')
    expect(analysisError(unavailable)).not.toContain('内部诊断')
    expect(analysisError(failure(400, 'invalid_request'))).toContain('运行结果暂无法确认')
  })

  it('成功响应无法通过契约校验时提示核对已保存结果', () => {
    const parsed = runResponse.safeParse({ run: { status: '等待确认' } })
    expect(parsed.success).toBe(false)
    if (!parsed.success) expect(analysisError(parsed.error)).toContain('分析响应不符合约定')
    expect(analysisError(new Error('返回的运行与请求不一致'))).toBe('返回的运行与请求不一致')
    expect(analysisError(null)).toBe('分析结果暂无法确认。')
  })
})
