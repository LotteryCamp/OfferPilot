import { onScopeDispose, ref, shallowRef, watch, type Ref } from 'vue'

export function useMatterRead<T>(
  key: Ref<string>,
  read: ((key: string, signal: AbortSignal) => Promise<T>) | undefined,
) {
  const data = shallowRef<T>()
  const loading = ref(false)
  const error = shallowRef<unknown>()
  let sequence = 0
  let controller: AbortController | undefined

  async function reload() {
    const current = ++sequence
    controller?.abort()
    controller = new AbortController()
    data.value = undefined
    error.value = undefined
    loading.value = Boolean(read)
    if (!read) return
    try {
      const result = await read(key.value, controller.signal)
      if (current === sequence) data.value = result
    } catch (failure) {
      if (current === sequence && !controller.signal.aborted) error.value = failure
    } finally {
      if (current === sequence) loading.value = false
    }
  }

  watch(key, reload, { immediate: true })
  onScopeDispose(() => {
    ++sequence
    controller?.abort()
  })
  return { data, loading, error, reload }
}
