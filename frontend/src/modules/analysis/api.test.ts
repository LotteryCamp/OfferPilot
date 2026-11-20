import { AxiosError, AxiosHeaders } from 'axios'
import { describe, expect, it } from 'vitest'
import { isConsentRejectedStart } from './api'

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
