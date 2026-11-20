import { z } from 'zod'

export const selfCheckSchema = z.object({
  conclusion: z.string().min(1),
  reason: z.string().min(1),
  missing_fields: z.array(z.string()),
  computed_deadline_at: z.string().nullable(),
  gaps: z.array(
    z.object({
      gap_type: z.string().min(1),
      description: z.string().min(1),
      locator: z.string().nullable(),
      source_id: z.uuid().nullable(),
      snapshot_id: z.uuid().nullable(),
    }),
  ),
})

export const optionalSelfCheckSchema = selfCheckSchema.nullable().optional()

const conclusions: Record<string, string> = {
  matched: '按现有信息符合',
  not_matched: '按现有信息不符合',
  missing_info: '待补充信息',
  needs_user_review: '待用户核对',
}

export function selfCheckLabel(value: string) {
  return Object.hasOwn(conclusions, value) ? conclusions[value]! : `待识别结论（${value}）`
}

export function selfCheckTone(value: string): 'success' | 'danger' | 'warning' | 'info' {
  if (value === 'matched') return 'success'
  if (value === 'not_matched') return 'danger'
  if (value === 'missing_info' || value === 'needs_user_review') return 'warning'
  return 'info'
}
