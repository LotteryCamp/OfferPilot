import { describe, expect, it } from 'vitest'
import { analysisTriggerBlockReason } from './trigger'

describe('排名保存后的分析衔接', () => {
  it('父组件尚未刷新保存状态时，已验证排名的衔接可继续', () => {
    expect(analysisTriggerBlockReason(true, '', 'saved-ranking')).toBe('')
  })
  it('用户直接点击仍受保存互斥约束', () => {
    expect(analysisTriggerBlockReason(true, '', 'manual')).not.toBe('')
    expect(analysisTriggerBlockReason(false, '', 'manual')).toBe('')
  })
  it.each(['分析正在执行', '授权不可用', '来源无效', '年度不一致', '会话存储不可用'])(
    '保存后的衔接仍保留限制：%s',
    (reason) => {
      expect(analysisTriggerBlockReason(true, reason, 'saved-ranking')).toBe(reason)
      expect(analysisTriggerBlockReason(false, reason, 'manual')).toBe(reason)
    },
  )
})
