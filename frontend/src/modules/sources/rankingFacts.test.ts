import { describe, expect, it } from 'vitest'
import {
  assertSavedRanking,
  assertRankingScope,
  sameRankingVersion,
  rankingFact,
  rankingReadResponse,
  rankingSaveInput,
  rankingSaveResponse,
} from './rankingFacts'

const saved = {
  id: '90000000-0000-4000-8000-000000000001',
  matter_id: 'a0000000-0000-4000-8000-000000000001',
  fact_type: 'gpa.rank',
  value: { position: 18, cohort_size: 120, percentile: 15 },
  value_text: '18/120',
  scope: null,
  valid_from: null,
  trust_level: 'self',
  status: 'confirmed',
  version_no: 1,
  value_hash: 'a'.repeat(64),
  confirmed_at: '2026-11-20T00:00:00Z',
  superseded_at: null,
  created_at: '2026-11-20T00:00:00Z',
}

describe('后端成绩排名协议', () => {
  it('当前记录与历史记录均须属于请求事项', () => {
    const fact = rankingFact.parse(saved)
    expect(() => assertRankingScope([fact], saved.matter_id)).not.toThrow()
    expect(() => assertRankingScope([fact], crypto.randomUUID())).toThrow()
    expect(() =>
      assertRankingScope([fact, { ...fact, matter_id: crypto.randomUUID() }], saved.matter_id),
    ).toThrow()
  })
  it('重读须匹配事实ID、事项、版本和内容指纹', () => {
    const fact = rankingFact.parse(saved)
    expect(sameRankingVersion(fact, { ...fact })).toBe(true)
    expect(sameRankingVersion(fact, { ...fact, version_no: 2 })).toBe(false)
    expect(sameRankingVersion(fact, { ...fact, id: crypto.randomUUID() })).toBe(false)
    expect(sameRankingVersion(fact, { ...fact, matter_id: crypto.randomUUID() })).toBe(false)
    expect(sameRankingVersion(fact, { ...fact, value_hash: 'b'.repeat(64) })).toBe(false)
    expect(sameRankingVersion(null, fact)).toBe(false)
    expect(sameRankingVersion(null, null)).toBe(true)
  })
  it('将前15%按百分数读取，不接受与名次不符的小数比例', () => {
    expect(rankingFact.parse(saved).value.percentile).toBe(15)
    expect(
      rankingFact.safeParse({ ...saved, value: { ...saved.value, percentile: 0.15 } }).success,
    ).toBe(false)
  })
  it('保留仅有百分位的记录，不反推出名次或人数', () => {
    const fact = rankingFact.parse({
      ...saved,
      value: { position: null, cohort_size: null, percentile: 15 },
    })
    expect(fact.value.position).toBeNull()
    expect(fact.value.cohort_size).toBeNull()
  })
  it('允许服务端四位小数舍入及极小比例舍入为零', () => {
    expect(
      rankingFact.safeParse({
        ...saved,
        value: { position: 1, cohort_size: 3, percentile: 33.3333 },
      }).success,
    ).toBe(true)
    expect(
      rankingFact.safeParse({
        ...saved,
        value: { position: 1, cohort_size: 10000000, percentile: 0 },
      }).success,
    ).toBe(true)
  })
  it('无当前记录返回空值，当前版本须与历史一致', () => {
    expect(rankingReadResponse.parse({ fact: null, versions: [] }).fact).toBeNull()
    expect(rankingReadResponse.safeParse({ fact: saved, versions: [saved] }).success).toBe(true)
    expect(rankingReadResponse.safeParse({ fact: saved, versions: [] }).success).toBe(false)
    expect(rankingReadResponse.safeParse({ fact: null, versions: [saved] }).success).toBe(false)
  })
  it('提交使用position/cohort_size，拒绝非法范围和旧字段', () => {
    const input = { value: { position: 18, cohort_size: 120 }, scope: null, valid_from: null }
    expect(rankingSaveInput.parse(input)).toEqual(input)
    expect(
      rankingSaveInput.safeParse({ ...input, value: { position: 121, cohort_size: 120 } }).success,
    ).toBe(false)
    expect(
      rankingSaveInput.safeParse({ ...input, value: { rank_position: 18, total_students: 120 } })
        .success,
    ).toBe(false)
  })
  it('保存响应须匹配提交内容并保留受影响候选', () => {
    const result = rankingSaveResponse.parse({
      fact: saved,
      created: false,
      affected_plans: [
        {
          plan_id: 'e0000000-0000-4000-8000-000000000001',
          matter_id: 'a0000000-0000-4000-8000-000000000001',
          version_no: 1,
          stored_version_no: null,
        },
      ],
    })
    expect(result.affected_plans).toHaveLength(1)
    const input = { value: { position: 18, cohort_size: 120 }, scope: null, valid_from: null }
    expect(() => assertSavedRanking(result.fact, input)).not.toThrow()
    expect(() => assertSavedRanking(result.fact, { ...input, scope: '不同统计范围' })).toThrow()
    expect(() =>
      assertSavedRanking(result.fact, { ...input, value: { position: 19, cohort_size: 120 } }),
    ).toThrow()
  })
})
