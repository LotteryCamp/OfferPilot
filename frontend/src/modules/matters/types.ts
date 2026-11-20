import { z } from 'zod'

export const matterStatusSchema = z.enum(['draft', 'active', 'paused', 'archived', 'cancelled'])
export const planStatusSchema = z.enum(['draft', 'pending', 'confirmed', 'rejected', 'expired'])
export const createMatterSchema = z.object({
  goal: z.string().trim().min(1, '请填写事项目标').max(200, '事项目标最多 200 字'),
  type_code: z.literal('pre_recommend'),
  scope_year: z
    .number()
    .int('请填写整数年度')
    .min(2020, '年度须为 2020—2100')
    .max(2100, '年度须为 2020—2100'),
  scope_attrs: z.record(z.string(), z.unknown()),
})
export const matterSchema = z.object({
  id: z.string().uuid(),
  workspace_id: z.string().uuid(),
  type_code: z.string(),
  type_name: z.string(),
  goal: z.string().min(1),
  status: matterStatusSchema,
  scope_year: z.number().int().nullable(),
  scope_attrs: z.record(z.string(), z.unknown()).nullable(),
  archived_at: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
  tasks: z.object({
    total: z.number().int().nonnegative(),
    done: z.number().int().nonnegative(),
    open: z.number().int().nonnegative(),
  }),
  latest_plan: z
    .object({
      id: z.string().uuid(),
      status: planStatusSchema,
      version_no: z.number().int().positive(),
    })
    .nullable(),
})

export type Matter = z.infer<typeof matterSchema>
export type CreateMatterInput = z.infer<typeof createMatterSchema>

export function matterYearLabel(year: Matter['scope_year']) {
  return year === null ? '适用年度未填写' : `${year} 年`
}

export interface MattersApi {
  list(signal: AbortSignal): Promise<Matter[]>
  read(id: string, signal: AbortSignal): Promise<Matter>
  create(input: CreateMatterInput): Promise<Matter>
}

export const matterStatusLabels: Record<Matter['status'], string> = {
  draft: '草稿',
  active: '进行中',
  paused: '已暂停',
  archived: '已归档',
  cancelled: '已取消',
}
export const planStatusLabels: Record<z.infer<typeof planStatusSchema>, string> = {
  draft: '草稿',
  pending: '待本人审阅',
  confirmed: '已确认',
  rejected: '已拒绝',
  expired: '已过期',
}
