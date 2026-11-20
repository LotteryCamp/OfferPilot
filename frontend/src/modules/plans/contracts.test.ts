import { describe, expect, it } from 'vitest'
import { assertDecision, canConfirmBasis, decisionResponse, planListResponse } from './contracts'

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

describe('候选的个人事实版本', () => {
  const staleFact = {
    fact_type: 'gpa.rank',
    stored_version_no: 1,
    current_version_no: 2,
    current_fact_id: '90000000-0000-4000-8000-000000000001',
  }
  it('读取计划列表时保留过期依据与具体版本', () => {
    const { plans } = planListResponse.parse({
      plans: [
        {
          id: planId,
          matter_id: matterId,
          version_no: 1,
          status: 'pending',
          basis_version: 'basis',
          generated_at: '2026-11-20T00:00:00Z',
          decision: null,
          basis_status: 'stale',
          stale_facts: [staleFact],
        },
      ],
    })
    expect(plans[0]?.stale_facts).toEqual([staleFact])
    expect(canConfirmBasis(plans[0]!)).toBe(false)
  })
  it('首次补录和事实不可用同样阻止按旧依据确认', () => {
    expect(canConfirmBasis({ basis_status: 'stale', stale_facts: [] })).toBe(false)
    expect(canConfirmBasis({ stale_facts: [{ ...staleFact, stored_version_no: null }] })).toBe(
      false,
    )
    expect(
      canConfirmBasis({
        stale_facts: [{ ...staleFact, current_version_no: null, current_fact_id: null }],
      }),
    ).toBe(false)
  })
  it('旧接口未返回依据状态时保持未知，由服务端作最终校验', () => {
    expect(canConfirmBasis({})).toBe(true)
    expect(canConfirmBasis({ basis_status: 'current', stale_facts: [] })).toBe(true)
    expect(canConfirmBasis({ basis_status: 'not_applicable', stale_facts: [] })).toBe(true)
  })
})
