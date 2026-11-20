import { describe, expect, it } from 'vitest'
import { displayDate, normalizeMatterId, safeSourceUrl, statusLabel } from './presentation'

describe('来源外链', () => {
  it.each([
    'javascript:alert(1)',
    'data:text/html,test',
    '//example.com',
    'https://user:pass@example.com',
    'not a URL',
  ])('拒绝非网页或携带凭据的链接 %s', (url) => expect(safeSourceUrl(url)).toBeNull())
  it('保留原文路径和定位', () => {
    const url = 'https://math.fzu.edu.cn/info/1171/10393.htm#section5'
    expect(safeSourceUrl(url)).toBe(url)
  })
})

describe('事项入口', () => {
  it('规范化有效 UUID', () => {
    expect(normalizeMatterId(' A0000000-0000-4000-8000-000000000001 ')).toBe(
      'a0000000-0000-4000-8000-000000000001',
    )
  })
  it.each(['../../other', 'undefined', '', ['a0000000-0000-4000-8000-000000000001']])(
    '拒绝无效路由参数 %s',
    (value) => expect(normalizeMatterId(value)).toBeNull(),
  )
})

describe('业务状态与时间', () => {
  it('未知状态保留待核对含义', () => {
    expect(statusLabel('check', 'unrecognized')).toContain('待识别')
    expect(statusLabel('check', 'constructor')).toContain('待识别')
    expect(statusLabel('check', 'passed')).toBe('程序检查通过')
    expect(statusLabel('extraction', 'checked')).toBe('已执行检查')
  })
  it('日期不附加时刻，缺失时间不生成当前时间', () => {
    expect(displayDate('2026-09-10')).toBe('2026-09-10')
    expect(displayDate(null)).toBe('未提供')
    expect(displayDate('invalid')).toBe('时间格式待核对')
    expect(displayDate('2026-02-30')).toBe('时间格式待核对')
  })
  it('UTC 时间转换为北京时间', () => {
    expect(displayDate('2026-09-10T07:00:00Z')).toContain('15:00')
    expect(displayDate('2026-09-10T07:00:00Z')).toContain('北京时间')
  })
  it.each(['2026-09-10T15:00:00', '2026-02-30T15:00:00Z', '09/10/2026'])(
    '不推断未约定的时间格式 %s',
    (value) => {
      expect(displayDate(value)).toBe('时间格式待核对')
    },
  )
})
