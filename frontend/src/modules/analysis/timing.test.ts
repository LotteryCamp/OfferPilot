import { describe, expect, it } from 'vitest'
import { agentRunTimeoutMs } from './timing'

describe('Agent 完整流程的等待预算', () => {
  it('默认覆盖两次180秒模型调用并留出来源读取及持久化时间', () => {
    expect(agentRunTimeoutMs()).toBeGreaterThan(2 * 180_000 + 45_000)
    expect(agentRunTimeoutMs('  ')).toBe(agentRunTimeoutMs())
  })
  it('允许部署按实际后端总耗时配置秒数', () => {
    expect(agentRunTimeoutMs('600')).toBe(600_000)
  })
  it.each(['0', '-1', 'NaN', 'Infinity', '0.5', '2147484'])('拒绝无效或溢出配置 %s', (value) => {
    expect(() => agentRunTimeoutMs(value)).toThrow('正整数秒数')
  })
})
