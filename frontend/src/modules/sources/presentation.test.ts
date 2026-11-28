import { describe, expect, it } from 'vitest'
import {
  displayDate,
  nextSnapshotId,
  normalizeMatterId,
  safeSourceUrl,
  statusLabel,
} from './presentation'
import type { Source } from './contracts'

function source(current: number): Source {
  const sourceId = 'b0000000-0000-4000-8000-000000000001'
  return {
    id: sourceId,
    publisher: '学校',
    url: 'https://example.edu/notice',
    scope: '本科生',
    scope_year: 2027,
    valid_from: null,
    valid_to: null,
    status: 'active',
    auto_check_status: 'passed',
    roi_status: 'original',
    last_fetched_at: null,
    snapshots: Array.from({ length: current }, (_, index) => ({
      id: `b0000000-0000-4000-8000-00000000000${index + 2}`,
      source_id: sourceId,
      version_no: index + 1,
      content_hash: 'a'.repeat(64),
      title: `通知 v${index + 1}`,
      published_date: null,
      text: null,
      fragments: [],
      fetched_at: null,
      is_current: index + 1 === current,
      requirements: [],
    })),
  }
}

describe('来源快照的刷新选择', () => {
  it('查看当前版本时，刷新后跟随新版本', () => {
    const before = source(1)
    const after = source(2)
    expect(nextSnapshotId(after, before, before.snapshots[0]!.id)).toBe(after.snapshots[1]!.id)
  })

  it('主动查看历史版本时，刷新后保留该选择', () => {
    const before = source(2)
    expect(nextSnapshotId(source(3), before, before.snapshots[0]!.id)).toBe(before.snapshots[0]!.id)
  })

  it('已选快照不在读取结果中时，选择当前版本', () => {
    const after = source(2)
    expect(nextSnapshotId(after, undefined, crypto.randomUUID())).toBe(after.snapshots[1]!.id)
  })

  it('来源或快照为空时清除选择', () => {
    expect(nextSnapshotId(undefined, source(1), crypto.randomUUID())).toBe('')
    expect(nextSnapshotId(source(0), source(1), crypto.randomUUID())).toBe('')
  })
})

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
