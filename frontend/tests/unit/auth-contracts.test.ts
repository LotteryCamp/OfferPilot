import { AxiosError, AxiosHeaders } from 'axios'
import { describe, expect, it } from 'vitest'
import { authFailure } from '../../src/modules/auth/api'
import { authenticatedAccountSchema } from '../../src/modules/auth/contracts'
import { SessionSyncError } from '../../src/shared/sessionCoordination'

function responseError(status: number, code: string, details?: unknown, retryAfter?: string) {
  const headers = new AxiosHeaders(retryAfter ? { 'Retry-After': retryAfter } : {})
  return new AxiosError('HTTP error', AxiosError.ERR_BAD_REQUEST, undefined, undefined, {
    status,
    statusText: '',
    data: { error: { code, message: '账户操作反馈', details } },
    headers,
    config: { headers: new AxiosHeaders() },
  })
}

describe('账户 API 错误响应解释', () => {
  it.each([
    [401, 'authentication_required'],
    [401, 'invalid_credentials'],
    [401, 'invalid_current_password'],
    [409, 'email_already_registered'],
    [429, 'too_many_login_attempts'],
  ])('保留 HTTP %s 与业务码 %s', (status, code) => {
    const failure = authFailure(responseError(status, code))
    expect(failure).toMatchObject({ status, code })
    expect(failure.message).not.toBe('账户操作反馈')
  })

  it('显示后端字段校验和限流重试时间', () => {
    const validation = authFailure(
      responseError(422, 'validation_error', {
        issues: [{ path: 'body.email', message: '邮箱格式无效' }],
      }),
    )
    expect(validation.fields).toEqual({ email: '邮箱格式无效' })
    expect(
      authFailure(responseError(429, 'too_many_login_attempts', undefined, '15')).retryAfter,
    ).toBe('15')
    const raw = responseError(429, 'too_many_login_attempts')
    if (!raw.response) throw new Error('缺少 HTTP 错误响应')
    raw.response.headers = { 'retry-after': '20' }
    expect(authFailure(raw).retryAfter).toBe('20')
  })

  it('服务异常或浏览器同步失败有独立反馈', () => {
    expect(authFailure(responseError(500, 'internal_error')).code).toBe('service_unavailable')
    expect(authFailure(new AxiosError('Network Error')).code).toBe('service_unavailable')
    expect(authFailure(new SessionSyncError('站点存储不可用'))).toEqual({
      code: 'session_sync_unavailable',
      message: '站点存储不可用',
    })
    expect(authFailure(new Error('response')).code).toBe('unverified_response')
  })
})

describe('真实认证响应契约', () => {
  it('认证响应缺少身份或会话时失败', () => {
    expect(authenticatedAccountSchema.safeParse({}).success).toBe(false)
    expect(authenticatedAccountSchema.safeParse({ user: null, session: null }).success).toBe(false)
  })
})
