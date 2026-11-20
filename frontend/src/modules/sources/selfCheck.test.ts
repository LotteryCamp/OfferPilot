import { describe, expect, it } from 'vitest'
import {
  optionalSelfCheckSchema,
  selfCheckLabel,
  selfCheckSchema,
  selfCheckTone,
} from './selfCheck'

describe('要求自查结果保存协议', () => {
  it.each([
    ['matched', '按现有信息符合', 'success'],
    ['not_matched', '按现有信息不符合', 'danger'],
    ['missing_info', '待补充信息', 'warning'],
    ['needs_user_review', '待用户核对', 'warning'],
  ])('独立显示结论 %s', (conclusion, label, tone) => {
    expect(selfCheckLabel(conclusion)).toBe(label)
    expect(selfCheckTone(conclusion)).toBe(tone)
  })

  it('未返回结果或明确为空时保持没有自查结果', () => {
    expect(optionalSelfCheckSchema.parse(undefined)).toBeUndefined()
    expect(optionalSelfCheckSchema.parse(null)).toBeNull()
  })

  it('未知结论保留编码并使用中性提示', () => {
    expect(selfCheckLabel('new_conclusion')).toBe('待识别结论（new_conclusion）')
    expect(selfCheckLabel('constructor')).toContain('待识别')
    expect(selfCheckTone('new_conclusion')).toBe('info')
  })

  it('保留规范字段、缺口定位和来源关联', () => {
    const result = {
      conclusion: 'missing_info',
      reason: '缺少已确认的英语成绩',
      missing_fields: ['cet6'],
      computed_deadline_at: null,
      gaps: [
        {
          gap_type: 'missing_personal_fact',
          description: '请补充已确认的英语成绩',
          locator: '二第5项',
          source_id: 'b0000000-0000-4000-8000-000000000101',
          snapshot_id: 'b0000000-0000-4000-8000-000000000102',
        },
      ],
    }
    expect(selfCheckSchema.parse(result)).toEqual(result)
    expect(selfCheckSchema.safeParse({ ...result, reason: '' }).success).toBe(false)
    expect(
      selfCheckSchema.safeParse({ ...result, gaps: [{ ...result.gaps[0], source_id: 'invalid' }] })
        .success,
    ).toBe(false)
  })
})
