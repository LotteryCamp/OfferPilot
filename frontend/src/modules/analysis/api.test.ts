import { AxiosError, AxiosHeaders } from 'axios'
import { describe, expect, it } from 'vitest'
import { analysisError, analysisInput, isConsentRejectedStart } from './api'

function failure(status: number, code: string) {
  return new AxiosError('请求被拒绝', 'ERR_BAD_REQUEST', undefined, undefined, {
    status,
    statusText: '',
    headers: {},
    config: { headers: new AxiosHeaders() },
    data: { error: { code } },
  })
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
