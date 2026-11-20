import { describe, expect, it } from 'vitest'
import { z } from 'zod'
import { chooseAttempt } from './attempt'

const matterId = 'a0000000-0000-4000-8000-000000000001'
const planId = 'e0000000-0000-4000-8000-000000000001'

describe('用户决定的操作标识', () => {
  it('首次决定生成合法且独立的 UUID', () => {
    const first = chooseAttempt(null, matterId, planId, 'confirm')
    const second = chooseAttempt(null, matterId, planId, 'confirm')
    expect(z.uuid().safeParse(first.key).success).toBe(true)
    expect(first.key).not.toBe(second.key)
  })
  it('同一决定的重试复用原标识', () => {
    const previous = chooseAttempt(null, matterId, planId, 'confirm')
    expect(chooseAttempt(previous, matterId, planId, 'confirm')).toBe(previous)
  })
  it('未确定结果时不能改做相反决定', () => {
    const previous = chooseAttempt(null, matterId, planId, 'confirm')
    expect(() => chooseAttempt(previous, matterId, planId, 'reject')).toThrow()
  })
  it('同一操作标识不能用于其他计划或事项', () => {
    const previous = chooseAttempt(null, matterId, planId, 'reject')
    expect(() => chooseAttempt(previous, matterId, crypto.randomUUID(), 'reject')).toThrow()
    expect(() => chooseAttempt(previous, crypto.randomUUID(), planId, 'reject')).toThrow()
  })
})
