import { onUnmounted, ref, watch } from 'vue'
import {
  analysisError,
  getAnalysis,
  isConsentRejectedStart,
  isMissingRun,
  startAnalysis,
} from './api'
import type { AnalysisInput } from './api'
import { canStartAnotherRun, restoreAnalysisAttempt } from './contracts'
import type { AnalysisAttempt, AnalysisRun } from './contracts'
import { workspaceStorageKey } from '../../shared/workspaceStorage'

export function useAnalysis(matterId: () => string, onRead: () => void) {
  const run = ref<AnalysisRun | null>(null)
  const attempt = ref<AnalysisAttempt | null>(null)
  const busy = ref(false)
  const checking = ref(false)
  const error = ref('')
  const storageReady = ref(true)
  let generation = 0
  let controller: AbortController | undefined
  const storageKey = (id: string) => workspaceStorageKey(`analysis:${id}`)

  function save(value: AnalysisAttempt) {
    sessionStorage.setItem(storageKey(value.matterId), JSON.stringify(value))
    attempt.value = value
  }

  function remember(value: AnalysisAttempt) {
    attempt.value = value
    try {
      save(value)
    } catch {
      storageReady.value = false
      error.value = '运行状态已读取，但浏览器无法保存运行标识；请先核对已保存结果。'
    }
  }

  async function check() {
    const id = attempt.value?.runId
    if (!id || busy.value || checking.value) return
    const ticket = generation
    controller = new AbortController()
    checking.value = true
    error.value = ''
    try {
      const result = await getAnalysis(id, controller.signal)
      if (ticket !== generation) return
      run.value = result
      if (attempt.value) remember({ ...attempt.value, status: result.status })
      onRead()
    } catch (cause) {
      if (ticket !== generation) return
      if (isMissingRun(cause)) {
        run.value = null
        if (attempt.value) remember({ ...attempt.value, runId: null, status: '不可查询' })
        error.value =
          '上次运行已找不到，可能因服务重启或运行中断。请读取已保存结果，也可重新发起分析。'
      } else error.value = analysisError(cause)
    } finally {
      if (ticket === generation) checking.value = false
    }
  }

  async function start(sourceId: string, input: Omit<AnalysisInput, 'operation_id'>) {
    if (busy.value || checking.value) {
      error.value = '已有分析正在执行或查询，请等待当前操作结束。'
      return null
    }
    if (!storageReady.value) {
      error.value = '会话存储不可用，尚未发起分析，请先检查浏览器设置。'
      return null
    }
    if (
      !canStartAnotherRun(
        run.value?.status ?? (attempt.value?.status === '不可查询' ? null : attempt.value?.status),
      )
    ) {
      error.value = `当前运行状态不允许再次发起：${run.value?.status ?? attempt.value?.status}`
      return null
    }
    const context = matterId()
    const ticket = generation
    error.value = ''
    const current: AnalysisAttempt = {
      matterId: context,
      sourceId,
      operationId: crypto.randomUUID(),
      runId: null,
      status: null,
    }
    try {
      save(current)
    } catch {
      storageReady.value = false
      error.value = '浏览器无法保存运行标识，尚未发起分析。请检查会话存储设置。'
      return null
    }
    run.value = null
    busy.value = true
    controller = new AbortController()
    try {
      const result = await startAnalysis(
        context,
        { ...input, operation_id: current.operationId },
        controller.signal,
      )
      if (ticket !== generation) return null
      run.value = result
      remember({ ...current, runId: result.run_id, status: result.status })
      onRead()
      return result
    } catch (cause) {
      if (ticket === generation) {
        if (isConsentRejectedStart(cause)) remember({ ...current, status: '未发起' })
        error.value = analysisError(cause)
      }
      return null
    } finally {
      if (ticket === generation) busy.value = false
    }
  }

  watch(
    matterId,
    (id) => {
      generation++
      controller?.abort()
      busy.value = false
      checking.value = false
      run.value = null
      attempt.value = null
      error.value = ''
      storageReady.value = true
      try {
        const raw = sessionStorage.getItem(storageKey(id))
        if (!raw) return
        const value = restoreAnalysisAttempt(raw, id)
        attempt.value = value
        if (value.runId) void check()
        else if (value.status === null)
          error.value = '上次分析请求结果尚未确认，请先刷新已保存的来源和候选结果。'
        else if (value.status === '不可查询')
          error.value = '上次运行已不可查询，请读取已保存结果或重新发起分析。'
        else if (value.status === '未发起')
          error.value = '上次分析因授权未通过而尚未发起，请核对当前授权后重试。'
      } catch {
        storageReady.value = false
        error.value = '浏览器中的运行标识无法核验，当前仅可读取已保存的来源和候选。'
      }
    },
    { immediate: true },
  )
  onUnmounted(() => {
    generation++
    controller?.abort()
  })
  return { run, attempt, busy, checking, error, storageReady, start, check }
}
