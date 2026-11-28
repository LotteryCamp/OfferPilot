import { describe, expect, it } from 'vitest'
import {
  assertDecision,
  assertPlanScope,
  canConfirmBasis,
  decisionResponse,
  planListResponse,
  planResponse,
} from './contracts'

const matterId = 'a0000000-0000-4000-8000-000000000001'
const planId = 'e0000000-0000-4000-8000-000000000001'
const key = '70000000-0000-4000-8000-000000000001'

function candidate(selfCheck: unknown) {
  return {
    plan: {
      id: planId,
      matter_id: matterId,
      version_no: 1,
      status: 'pending',
      basis_version: 'basis',
      generated_at: '2026-11-26T00:00:00Z',
      decision: null,
      matter: { id: matterId, goal: '推免准备', scope_year: 2027, scope_attrs: {} },
      items: [
        {
          id: 'e0000000-0000-4000-8000-000000000002',
          seq: 1,
          title: '核对申请条件',
          detail: null,
          obligation_nature: 'required',
          official_deadline_date: null,
          official_deadline_at: null,
          suggested_date: null,
          depends_on_item_ids: [],
          evidence_required: false,
          requirement: {
            id: 'b0000000-0000-4000-8000-000000000001',
            label: '成绩排名',
            extract_status: 'to_review',
            self_check: selfCheck,
          },
          sources: [],
        },
      ],
      tasks: [],
    },
  }
}

describe('候选条目的自查依据', () => {
  it.each(['matched', 'not_matched', 'missing_info', 'needs_user_review'])(
    '保留 %s 的原因、缺项与缺口定位',
    (conclusion) => {
      const check = {
        conclusion,
        reason: '按当前事项已确认的事实核对',
        missing_fields: ['gpa.rank'],
        computed_deadline_at: null,
        gaps: [
          {
            gap_type: 'missing_personal_fact',
            description: '请补充本人排名',
            locator: '申请条件第2项',
            source_id: null,
            snapshot_id: null,
          },
        ],
      }
      const { plan } = planResponse.parse(candidate(check))
      expect(plan.items[0]?.requirement?.self_check).toEqual(check)
    },
  )

  it.each([undefined, null])('未提供自查结果时保持为空，不推断符合条件', (value) => {
    const { plan } = planResponse.parse(candidate(value))
    expect(plan.items[0]?.requirement?.self_check).toBe(value)
  })

  it('自查结果格式不完整时停止作为有效候选展示', () => {
    expect(planResponse.safeParse(candidate({ conclusion: 'matched' })).success).toBe(false)
  })
})

describe('计划与任务的事项归属', () => {
  function confirmedPlan() {
    const { plan } = planResponse.parse(candidate(null))
    plan.status = 'confirmed'
    plan.tasks = [
      {
        id: 'f0000000-0000-4000-8000-000000000001',
        matter_id: matterId,
        plan_id: planId,
        plan_item_id: plan.items[0]!.id,
        title: '核对申请条件',
        status: 'pending',
        official_deadline_date: null,
        official_deadline_at: null,
        suggested_date: null,
        depends_on: [],
      },
    ]
    return plan
  }

  it('接受同一事项下已确认计划的正式任务', () => {
    expect(() => assertPlanScope(confirmedPlan(), matterId, planId)).not.toThrow()
  })

  it.each(['id', 'matter_id', 'matter'] as const)('阻止计划的 %s 与当前上下文不一致', (field) => {
    const plan = confirmedPlan()
    if (field === 'matter') plan.matter.id = crypto.randomUUID()
    else plan[field] = crypto.randomUUID()
    expect(() => assertPlanScope(plan, matterId, planId)).toThrow('计划与当前事项不一致')
  })

  it.each(['matter_id', 'plan_id'] as const)('阻止任务的 %s 指向其他上下文', (field) => {
    const plan = confirmedPlan()
    plan.tasks[0]![field] = crypto.randomUUID()
    expect(() => assertPlanScope(plan, matterId, planId)).toThrow('计划任务归属不一致')
  })

  it.each(['pending', 'rejected', 'expired'])('阻止 %s 计划携带正式任务', (status) => {
    const plan = confirmedPlan()
    plan.status = status
    expect(() => assertPlanScope(plan, matterId, planId)).toThrow('未确认计划包含正式任务')
  })
})

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
