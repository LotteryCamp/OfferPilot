import { describe, expect, it } from 'vitest'
import { rankingDraftSchema, rankingPercentage } from './rankingDraft'

describe('当前事项排名补录输入', () => {
  const valid = { rankPosition: '18', totalStudents: '120', confirmed: true }

  it('接受本人确认的有效排名并计算比例', () => {
    const result = rankingDraftSchema.parse(valid)
    expect(rankingPercentage(result.rankPosition, result.totalStudents)).toBe('15%')
  })

  it.each(['', ' ', '0', '-1', '1.5', '1e2', 'Infinity', 'NaN', '9007199254740992'])(
    '拒绝非法排名或总人数 %j',
    (input) => {
      expect(rankingDraftSchema.safeParse({ ...valid, rankPosition: input }).success).toBe(false)
      expect(rankingDraftSchema.safeParse({ ...valid, totalStudents: input }).success).toBe(false)
    },
  )

  it('拒绝排名超过总人数并定位到排名字段', () => {
    const result = rankingDraftSchema.safeParse({ ...valid, rankPosition: '121' })
    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error.issues.some((issue) => issue.path[0] === 'rankPosition')).toBe(true)
    }
  })

  it('允许第一名和最后一名，不从排名比例推断资格结论', () => {
    expect(rankingDraftSchema.safeParse({ ...valid, rankPosition: '1' }).success).toBe(true)
    const last = rankingDraftSchema.parse({ ...valid, rankPosition: '120' })
    expect(rankingPercentage(last.rankPosition, last.totalStudents)).toBe('100%')
    expect(last).not.toHaveProperty('conclusion')
  })

  it('要求本人确认真实性', () => {
    expect(rankingDraftSchema.safeParse({ ...valid, confirmed: false }).success).toBe(false)
  })

  it('未勾选本人确认时也能指出排名超出总人数', () => {
    const result = rankingDraftSchema.safeParse({ ...valid, rankPosition: '121', confirmed: false })
    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error.issues.map((issue) => issue.path[0])).toEqual([
        'confirmed',
        'rankPosition',
      ])
    }
  })

  it('接受数字首尾空白并保留整数精度', () => {
    expect(
      rankingDraftSchema.parse({ ...valid, rankPosition: ' 18 ', totalStudents: '120 ' }),
    ).toEqual({
      rankPosition: 18,
      totalStudents: 120,
      confirmed: true,
    })
  })

  it('展示重复小数和极小比例，避免有效排名显示为零', () => {
    expect(rankingPercentage(1, 3)).toBe('33.33%')
    expect(rankingPercentage(1, 100000)).toBe('小于 0.01%')
  })
})
