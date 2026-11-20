import { effectScope, nextTick, ref } from 'vue'
import { describe, expect, it } from 'vitest'
import { useMatterRead } from '../../src/modules/matters/useMatterRead'

describe('事项上下文刷新', () => {
  it('同一事项刷新期间保留上下文，刷新成功后替换结果', async () => {
    const scope = effectScope()
    const key = ref('first')
    const pending: Array<(value: string) => void> = []
    const state = scope.run(() =>
      useMatterRead(key, () => new Promise<string>((resolve) => pending.push(resolve))),
    )!
    try {
      pending.shift()!('before')
      await nextTick()
      expect(state.data.value).toBe('before')
      const refresh = state.reload()
      expect(state.data.value).toBe('before')
      expect(state.loading.value).toBe(true)
      pending.shift()!('after')
      await refresh
      expect(state.data.value).toBe('after')
    } finally {
      scope.stop()
    }
  })

  it('切换事项立即清除旧上下文，晚到的旧读取不会覆盖新事项', async () => {
    const scope = effectScope()
    const key = ref('first')
    const pending = new Map<string, (value: string) => void>()
    const state = scope.run(() =>
      useMatterRead(key, (id) => new Promise<string>((resolve) => pending.set(id, resolve))),
    )!
    try {
      const oldRead = pending.get('first')!
      key.value = 'second'
      await nextTick()
      expect(state.data.value).toBeUndefined()
      pending.get('second')!('second')
      await nextTick()
      oldRead('first')
      await nextTick()
      expect(state.data.value).toBe('second')
    } finally {
      scope.stop()
    }
  })

  it('同事项重读失败后清除上下文，停止业务页面继续使用旧事项', async () => {
    const scope = effectScope()
    const key = ref('first')
    let available = true
    const state = scope.run(() =>
      useMatterRead(key, async () => {
        if (!available) throw new Error('unavailable')
        return key.value
      }),
    )!
    try {
      await nextTick()
      expect(state.data.value).toBe('first')
      available = false
      await state.reload()
      expect(state.data.value).toBeUndefined()
      expect(state.error.value).toBeInstanceOf(Error)
    } finally {
      scope.stop()
    }
  })
})
