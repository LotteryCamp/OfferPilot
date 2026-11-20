import { describe, expect, it } from 'vitest'
import { assertDecision, decisionResponse } from './contracts'

const matterId = 'a0000000-0000-4000-8000-000000000001'
const planId = 'e0000000-0000-4000-8000-000000000001'
const key = '70000000-0000-4000-8000-000000000001'

function rejection() {
  return decisionResponse.parse({
    plan_id: planId,
    status: 'rejected',
    replayed: false,
    tasks: [],
    decision: {
      plan_id: planId,
      decision: 'rejected',
      decided_by: '00000000-0000-7000-8000-000000000001',
      decided_at: '2026-09-09T01:05:00+00:00',
      operation_id: key,
    },
  })
}

describe('决定响应的一致性', () => {
  it('接受与当前计划和操作标识一致的拒绝响应', () => {
    expect(() => assertDecision(rejection(), matterId, planId, 'reject', key)).not.toThrow()
  })
  it('重放响应仍须对应同一操作', () => {
    const result = rejection()
    result.replayed = true
    expect(() => assertDecision(result, matterId, planId, 'reject', key)).not.toThrow()
    expect(() => assertDecision(result, matterId, planId, 'reject', crypto.randomUUID())).toThrow()
  })
  it('其他计划的响应和相反决定不能报成功', () => {
    expect(() =>
      assertDecision(rejection(), matterId, crypto.randomUUID(), 'reject', key),
    ).toThrow()
    expect(() => assertDecision(rejection(), matterId, planId, 'confirm', key)).toThrow()
  })
})
