import { z } from 'zod'

const id = z.uuid()
const text = z.string().nullable()
const decision = z.object({
  decision: z.enum(['confirmed', 'rejected']),
  decided_by: id,
  decided_at: z.string(),
  operation_id: id,
})
const summary = z.object({
  id,
  matter_id: id,
  version_no: z.number().int().positive(),
  status: z.string(),
  basis_version: z.string(),
  generated_at: z.string(),
  decision: decision.nullable(),
})
const citation = z.object({
  source_id: id,
  snapshot_id: id,
  publisher: z.string(),
  url: z.string(),
  source_status: z.string(),
  version_no: z.number().int().positive(),
  fetched_at: text,
  is_current: z.boolean(),
  locator: z.string(),
  quote: text,
})
const task = z.object({
  id,
  matter_id: id,
  plan_id: id,
  plan_item_id: id,
  title: z.string(),
  status: z.string(),
  official_deadline_date: text,
  official_deadline_at: text,
  suggested_date: text,
  depends_on: z.array(id),
})
export const planListResponse = z.object({ plans: z.array(summary) })
export const planResponse = z.object({
  plan: summary.extend({
    matter: z.object({
      id,
      goal: z.string(),
      scope_year: z.number().int().nullable(),
      scope_attrs: z.record(z.string(), z.unknown()).nullable(),
    }),
    items: z.array(
      z.object({
        id,
        seq: z.number().int().positive(),
        title: z.string(),
        detail: text,
        obligation_nature: z.string(),
        official_deadline_date: text,
        official_deadline_at: text,
        suggested_date: text,
        depends_on_item_ids: z.array(id),
        evidence_required: z.boolean(),
        requirement: z.object({ id, label: z.string(), extract_status: z.string() }).nullable(),
        sources: z.array(citation),
      }),
    ),
    tasks: z.array(task),
  }),
})
export const taskResponse = z.object({
  tasks: z.array(task.extend({ sources: z.array(citation) })),
})
export const decisionResponse = z.object({
  plan_id: id,
  status: z.enum(['confirmed', 'rejected']),
  decision: decision.extend({ plan_id: id }),
  tasks: z.array(task),
  replayed: z.boolean(),
})
export type Plan = z.infer<typeof planResponse>['plan']
export type PlanSummary = z.infer<typeof summary>
export type Task = z.infer<typeof taskResponse>['tasks'][number]
export type DecisionResult = z.infer<typeof decisionResponse>
export type Action = 'confirm' | 'reject'

export function assertPlanScope(plan: Plan, matterId: string, planId: string) {
  if (plan.id !== planId || plan.matter_id !== matterId || plan.matter.id !== matterId) {
    throw new Error('计划与当前事项不一致，已停止展示。')
  }
  if (plan.tasks.some((item) => item.matter_id !== matterId || item.plan_id !== planId)) {
    throw new Error('计划任务归属不一致，已停止展示。')
  }
  if (plan.status !== 'confirmed' && plan.tasks.length) {
    throw new Error('未确认计划包含正式任务，请联系后端核对。')
  }
}

export function assertDecision(
  result: DecisionResult,
  matterId: string,
  planId: string,
  action: Action,
  key: string,
) {
  const expected = action === 'confirm' ? 'confirmed' : 'rejected'
  if (
    result.plan_id !== planId ||
    result.decision.plan_id !== planId ||
    result.status !== expected ||
    result.decision.decision !== expected ||
    result.decision.operation_id !== key ||
    result.tasks.some((item) => item.matter_id !== matterId || item.plan_id !== planId) ||
    (action === 'reject' && result.tasks.length !== 0)
  ) {
    throw new Error('决定响应与当前操作不一致，请重新读取计划状态。')
  }
}
