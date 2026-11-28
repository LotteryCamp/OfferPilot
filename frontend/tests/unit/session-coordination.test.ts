import { describe, expect, it } from 'vitest'
import { isCurrentSessionRevision } from '../../src/shared/sessionCoordination'

describe('账户会话版本', () => {
  it('允许已确认且稳定的会话版本', () => {
    expect(
      isCurrentSessionRevision('revision-1', { revision: 'revision-1', changing: false }),
    ).toBe(true)
  })

  it.each([
    [null, { revision: 'revision-1', changing: false }],
    ['revision-1', { revision: 'revision-2', changing: false }],
    ['revision-1', { revision: 'revision-1', changing: true }],
  ] as const)('须等待当前稳定会话确认', (expected, current) => {
    expect(isCurrentSessionRevision(expected, current)).toBe(false)
  })
})
