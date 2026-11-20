import { z } from 'zod'

const positiveInteger = z.number().int().positive().max(Number.MAX_SAFE_INTEGER)
const rankValue = z
  .object({
    position: positiveInteger.nullable(),
    cohort_size: positiveInteger.nullable(),
    percentile: z.number().min(0).max(100),
  })
  .superRefine((value, ctx) => {
    if ((value.position === null) !== (value.cohort_size === null)) {
      ctx.addIssue({ code: 'custom', message: '排名与总人数应同时提供或同时为空。' })
    }
    if (value.position !== null && value.cohort_size !== null) {
      const expected = (value.position / value.cohort_size) * 100
      if (value.position > value.cohort_size || Math.abs(expected - value.percentile) > 0.000051) {
        ctx.addIssue({ code: 'custom', message: '排名、总人数和百分位不一致。' })
      }
    }
  })

export const rankingFact = z.object({
  id: z.uuid(),
  fact_type: z.literal('gpa.rank'),
  value: rankValue,
  value_text: z.string(),
  scope: z.string().nullable(),
  valid_from: z.iso.date().nullable(),
  trust_level: z.literal('self'),
  status: z.enum(['confirmed', 'superseded']),
  version_no: positiveInteger,
  value_hash: z.string().regex(/^[0-9a-f]{64}$/),
  confirmed_at: z.string(),
  superseded_at: z.string().nullable(),
  created_at: z.string(),
})
export const rankingReadResponse = z
  .object({
    fact: rankingFact.nullable(),
    versions: z.array(rankingFact),
  })
  .superRefine(({ fact, versions }, ctx) => {
    const confirmed = versions.filter((entry) => entry.status === 'confirmed')
    if (
      fact === null
        ? confirmed.length !== 0
        : fact.status !== 'confirmed' ||
          confirmed.length !== 1 ||
          confirmed[0]?.id !== fact.id ||
          confirmed[0]?.version_no !== fact.version_no ||
          confirmed[0]?.value_hash !== fact.value_hash
    ) {
      ctx.addIssue({ code: 'custom', message: '当前排名与版本历史不一致，请重新读取。' })
    }
  })
export const rankingSaveInput = z.strictObject({
  value: z
    .strictObject({ position: positiveInteger, cohort_size: positiveInteger })
    .refine((value) => value.position <= value.cohort_size, '排名不能超过总人数。'),
  scope: z.string().trim().max(200).nullable(),
  valid_from: z.iso.date().nullable(),
})
export const rankingSaveResponse = z.object({
  fact: rankingFact.refine((fact) => fact.status === 'confirmed', '保存结果须为当前确认版本。'),
  created: z.boolean(),
  affected_plans: z.array(
    z.object({
      plan_id: z.uuid(),
      matter_id: z.uuid(),
      version_no: positiveInteger,
      stored_version_no: positiveInteger.nullable(),
    }),
  ),
})
export type RankingFact = z.infer<typeof rankingFact>
export type RankingSaveInput = z.infer<typeof rankingSaveInput>

export function assertSavedRanking(fact: RankingFact, input: RankingSaveInput) {
  if (
    fact.value.position !== input.value.position ||
    fact.value.cohort_size !== input.value.cohort_size ||
    fact.scope !== (input.scope?.trim() || null) ||
    fact.valid_from !== input.valid_from
  )
    throw new Error('保存响应与提交的排名不一致，请重新读取后核对。')
}
