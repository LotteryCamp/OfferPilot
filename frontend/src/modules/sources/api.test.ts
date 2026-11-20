import { describe, expect, it } from 'vitest'
import { z } from 'zod'
import { isRetryableReadStatus, readFailure } from './api'

describe('来源读取状态策略', () => {
  it.each([401, 403, 404, 400, 422])('HTTP %s 清除已展示的资料', (status) => {
    expect(isRetryableReadStatus(status)).toBe(false)
  })

  it.each([undefined, 408, 429, 500, 502, 503, 504])(
    '临时读取失败 %s 允许保留上次资料',
    (status) => {
      expect(isRetryableReadStatus(status)).toBe(true)
    },
  )

  it('数据格式不符合契约时停止展示', () => {
    const result = z.uuid().safeParse('invalid')
    expect(result.success).toBe(false)
    if (!result.success) {
      expect(readFailure(result.error).retainData).toBe(false)
    }
  })

  it('事项关联校验未通过时停止展示', () => {
    const failure = readFailure(new Error('返回事项与当前事项不一致，已停止展示。'))
    expect(failure.retainData).toBe(false)
  })
})
