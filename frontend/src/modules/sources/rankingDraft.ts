import { z } from 'zod'

export interface RankingDraft {
  rankPosition: string
  totalStudents: string
  confirmed: boolean
}

const positiveInteger = z
  .string()
  .trim()
  .regex(/^\d+$/, '请填写正整数')
  .transform(Number)
  .refine((value) => Number.isSafeInteger(value) && value > 0, '请填写有效的正整数')

export const rankingDraftSchema = z
  .object({
    rankPosition: positiveInteger,
    totalStudents: positiveInteger,
    confirmed: z.boolean().refine((value) => value, '请确认排名信息由本人核对且真实'),
  })
  .superRefine((value, context) => {
    if (value.rankPosition > value.totalStudents) {
      context.addIssue({
        code: 'custom',
        path: ['rankPosition'],
        message: '排名不能超过参与排名总人数',
      })
    }
  })

export function rankingPercentage(rankPosition: number, totalStudents: number): string {
  const percent = (rankPosition / totalStudents) * 100
  if (percent > 0 && percent < 0.01) return '小于 0.01%'
  return `${new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 }).format(percent)}%`
}
