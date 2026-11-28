import { AxiosError, AxiosHeaders } from 'axios'
import { describe, expect, it } from 'vitest'
import { decisionMayBeCommitted, decisionNeedsReload } from './api'

function failure(status: number, code: string) {
  return new AxiosError('决定未完成', 'ERR_BAD_REQUEST', undefined, undefined, {
    status,
    statusText: '',
    headers: {},
    config: { headers: new AxiosHeaders() },
    data: { error: { code, message: '请核对计划状态' } },
  })
}

describe('候选决定的状态恢复', () => {
  it.each([
    'basis_changed',
    'plan_expired',
    'plan_already_decided',
    'plan_not_pending',
    'official_deadline_passed',
    'basis_unresolved',
    'source_unavailable',
  ])('服务端返回 %s 后重读当前候选', (code) => {
    const error = failure(409, code)
    expect(decisionNeedsReload(error)).toBe(true)
    expect(decisionMayBeCommitted(error)).toBe(false)
  })

  it.each([408, 429, 500, 502, 504])('HTTP %s 保留原操作标识供核对和重试', (status) => {
    const error = failure(status, 'basis_changed')
    expect(decisionMayBeCommitted(error)).toBe(true)
    expect(decisionNeedsReload(error)).toBe(false)
  })

  it('连接中断或成功响应无法核验时，决定结果保持未知', () => {
    for (const error of [new AxiosError('连接中断'), new Error('决定响应与操作不一致')]) {
      expect(decisionMayBeCommitted(error)).toBe(true)
      expect(decisionNeedsReload(error)).toBe(false)
    }
  })

  it('操作标识冲突交由用户核对，不推断计划终态', () => {
    expect(decisionNeedsReload(failure(409, 'operation_conflict'))).toBe(false)
    expect(decisionNeedsReload(failure(401, 'authentication_required'))).toBe(false)
  })
})
