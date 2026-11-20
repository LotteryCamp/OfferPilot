import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Source } from './contracts'
import { readFailure, readSources } from './api'

export const useSourcesStore = defineStore('matter-sources', () => {
  const sources = ref<Source[]>([])
  const currentMatterId = ref('')
  const loading = ref(false)
  const error = ref('')
  const loadedAt = ref<string | null>(null)
  let controller: AbortController | undefined
  let request = 0

  function cancel() {
    request++
    controller?.abort()
    controller = undefined
    loading.value = false
  }

  function clearData() {
    sources.value = []
    loadedAt.value = null
  }

  async function load(matterId: string) {
    cancel()
    const currentRequest = request
    if (currentMatterId.value !== matterId) {
      clearData()
    }
    currentMatterId.value = matterId
    error.value = ''
    loading.value = true
    const requestController = new AbortController()
    controller = requestController
    try {
      const data = await readSources(matterId, requestController.signal)
      if (request !== currentRequest) return
      sources.value = data
      loadedAt.value = new Date().toISOString()
    } catch (cause) {
      if (request === currentRequest) {
        const failure = readFailure(cause)
        if (!failure.retainData) clearData()
        error.value = failure.message
      }
    } finally {
      requestController.abort()
      if (request === currentRequest) {
        controller = undefined
        loading.value = false
      }
    }
  }

  return { sources, currentMatterId, loading, error, loadedAt, load, cancel }
})
