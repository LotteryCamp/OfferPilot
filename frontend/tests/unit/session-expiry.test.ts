import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createSessionExpiryTimer } from '../../src/modules/auth/sessionExpiry'

describe('会话到期调度', () => {
  const start = Date.parse('2026-11-27T08:00:00Z')
  let expiry: string | undefined
  let checkedAt: number[]

  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(start)
    checkedAt = []
    expiry = undefined
  })

  afterEach(() => vi.useRealTimers())

  function finishSession() {
    checkedAt.push(Date.now())
    expiry = undefined
    return Promise.resolve()
  }

  it('在不足一分钟的实际到期时刻检查会话', async () => {
    expiry = new Date(start + 5_000).toISOString()
    const timer = createSessionExpiryTimer(() => expiry, finishSession)
    timer.refresh()

    await vi.advanceTimersByTimeAsync(4_999)
    expect(checkedAt).toEqual([])
    await vi.advanceTimersByTimeAsync(1)
    expect(checkedAt).toEqual([start + 5_000])
    timer.dispose()
  })

  it('记住登录的长会话在定时器上限处重新排期并在真实到期后检查', async () => {
    const duration = 30 * 24 * 60 * 60 * 1_000
    expiry = new Date(start + duration).toISOString()
    const timer = createSessionExpiryTimer(() => expiry, finishSession)
    timer.refresh()

    await vi.advanceTimersByTimeAsync(2_147_000_000)
    expect(checkedAt).toEqual([])
    await vi.advanceTimersByTimeAsync(duration - 2_147_000_000 - 1)
    expect(checkedAt).toEqual([])
    await vi.advanceTimersByTimeAsync(1)
    expect(checkedAt).toEqual([start + duration])
    timer.dispose()
  })

  it('重新排期后上一会话的定时器不会触发', async () => {
    expiry = new Date(start + 5_000).toISOString()
    const timer = createSessionExpiryTimer(() => expiry, finishSession)
    timer.refresh()
    expiry = new Date(start + 10_000).toISOString()
    timer.refresh()

    await vi.advanceTimersByTimeAsync(5_000)
    expect(checkedAt).toEqual([])
    await vi.advanceTimersByTimeAsync(5_000)
    expect(checkedAt).toEqual([start + 10_000])
    timer.dispose()
  })

  it('退出和组件销毁都会停止到期检查', async () => {
    expiry = new Date(start + 5_000).toISOString()
    const timer = createSessionExpiryTimer(() => expiry, finishSession)
    timer.refresh()
    expiry = undefined
    timer.refresh()
    await vi.advanceTimersByTimeAsync(5_000)
    expect(checkedAt).toEqual([])

    expiry = new Date(start + 15_000).toISOString()
    timer.refresh()
    timer.dispose()
    await vi.advanceTimersByTimeAsync(10_000)
    expect(checkedAt).toEqual([])
    expect(vi.getTimerCount()).toBe(0)
  })

  it('已过本机显示有效期但服务仍确认会话时有间隔地继续核对', async () => {
    expiry = new Date(start - 1).toISOString()
    const timer = createSessionExpiryTimer(
      () => expiry,
      () => {
        checkedAt.push(Date.now())
        return Promise.resolve()
      },
    )
    timer.refresh()

    await vi.advanceTimersByTimeAsync(0)
    expect(checkedAt).toEqual([start])
    await vi.advanceTimersByTimeAsync(9_999)
    expect(checkedAt).toEqual([start])
    await vi.advanceTimersByTimeAsync(1)
    expect(checkedAt).toEqual([start, start + 10_000])
    timer.dispose()
  })
})
