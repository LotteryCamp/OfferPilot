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
  let loadedKey: string | undefined

  async function reload() {
    const current = ++sequence
    controller?.abort()
    const request = new AbortController()
    controller = request
    const requestedKey = key.value
    if (loadedKey !== requestedKey) data.value = undefined
    error.value = undefined
    loading.value = Boolean(read)
    if (!read) return
    try {
      const result = await read(requestedKey, request.signal)
      if (current === sequence) {
        data.value = result
        loadedKey = requestedKey
      }
    } catch (failure) {
      if (current === sequence && !request.signal.aborted) {
        data.value = undefined
        error.value = failure
      }
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
