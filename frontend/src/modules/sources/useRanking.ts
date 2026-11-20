import { computed, nextTick, onUnmounted, reactive, ref, watch } from 'vue'
import type { AnalysisRun } from '../analysis/contracts'
import { runStatusText } from '../analysis/contracts'
import { AnalysisNotStartedError } from '../analysis/trigger'
import { readRanking, saveRanking, rankingError, rankingSaveMayHaveCommitted } from './rankingApi'
import { rankingDraftSchema } from './rankingDraft'
import { sameRankingVersion } from './rankingFacts'
import type { RankingFact } from './rankingFacts'

export function useRanking(
  matterId: () => string,
  onChanged: () => void,
  recheck: (sourceId: string | null) => Promise<AnalysisRun | null>,
  unavailable: () => string,
) {
  const draft = reactive({ rankPosition: '', totalStudents: '', confirmed: false })
  const saved = ref<RankingFact | null>(null)
  const ready = ref(false)
  const loading = ref(false)
  const phase = ref<'idle' | 'saving' | 'verifying' | 'rechecking'>('idle')
  const error = ref('')
  const notice = ref('')
  const uncertain = ref(false)
  const affected = ref(0)
  const busy = computed(() => phase.value !== 'idle')
  const writing = computed(() => ['saving', 'verifying'].includes(phase.value))
  const dirty = computed(
    () =>
      draft.rankPosition.trim() !== String(saved.value?.value.position ?? '') ||
      draft.totalStudents.trim() !== String(saved.value?.value.cohort_size ?? ''),
  )
  let generation = 0
  let controller: AbortController | undefined

  function hydrate() {
    draft.rankPosition = String(saved.value?.value.position ?? '')
    draft.totalStudents = String(saved.value?.value.cohort_size ?? '')
    draft.confirmed = false
  }

  async function load(hydrateInput = false) {
    if (busy.value || loading.value) return
    const ticket = generation
    const context = matterId()
    controller = new AbortController()
    loading.value = true
    ready.value = false
    error.value = ''
    notice.value = ''
    try {
      const result = await readRanking(context, controller.signal)
      if (ticket !== generation) return
      saved.value = result
      ready.value = true
      uncertain.value = false
      affected.value = 0
      if (hydrateInput) hydrate()
    } catch (cause) {
      if (ticket === generation) error.value = rankingError(cause)
    } finally {
      if (ticket === generation) loading.value = false
    }
  }

  async function runRecheck(sourceId: string | null) {
    const ticket = generation
    await nextTick()
    if (ticket !== generation) return
    const reason = unavailable()
    if (reason) {
      notice.value = `排名已保存，尚未重新自查：${reason}`
      return
    }
    phase.value = 'rechecking'
    const result = await recheck(sourceId)
    if (ticket !== generation) return
    notice.value = result
      ? `排名已保存。${runStatusText(result)} 请核对分析反馈及重新读取的条件结果。`
      : '排名已保存，重新自查尚未取得可确认的结果。请查看分析区原因，核对已保存结果后重试。'
  }

  async function saveAndRecheck(sourceId: string | null) {
    const parsed = rankingDraftSchema.safeParse(draft)
    if (!parsed.success || busy.value || loading.value || !ready.value) return
    const context = matterId()
    const ticket = generation
    controller = new AbortController()
    const signal = controller.signal
    error.value = ''
    notice.value = ''
    phase.value = 'verifying'
    let sent = false
    let acknowledged = false
    try {
      const current = await readRanking(context, signal)
      if (ticket !== generation) return
      if (!sameRankingVersion(current, saved.value)) {
        ready.value = false
        throw new Error('排名已在其他页面发生变化，请重新读取并核对后保存；当前输入已保留。')
      }
      phase.value = 'saving'
      sent = true
      const result = await saveRanking(
        context,
        {
          value: { position: parsed.data.rankPosition, cohort_size: parsed.data.totalStudents },
          scope: saved.value?.scope ?? null,
          valid_from: saved.value?.valid_from ?? null,
        },
        signal,
      )
      if (ticket !== generation) return
      acknowledged = true
      saved.value = result.fact
      affected.value = result.affected_plans.length
      onChanged()
      phase.value = 'verifying'
      const verified = await readRanking(context, signal)
      if (ticket !== generation) return
      if (!sameRankingVersion(verified, result.fact)) {
        throw new Error('保存后排名版本又发生变化，请重新读取核对，尚未发起重新自查。')
      }
      saved.value = verified
      hydrate()
      phase.value = 'idle'
      await runRecheck(sourceId)
    } catch (cause) {
      if (ticket !== generation) return
      error.value = rankingError(cause)
      if (cause instanceof AnalysisNotStartedError) {
        notice.value = `排名已保存，尚未重新自查：${cause.message}`
        return
      }
      if (acknowledged) {
        notice.value = '保存请求已确认；后续核对或重新自查未完成。请重新读取排名，输入已保留。'
        ready.value = false
      } else if (sent && rankingSaveMayHaveCommitted(cause)) {
        uncertain.value = true
        ready.value = false
        notice.value = '保存结果尚未确定，已保留输入。请先重新读取核对，暂不重复保存或发起自查。'
      }
    } finally {
      if (ticket === generation) phase.value = 'idle'
    }
  }

  async function recheckSaved(sourceId: string | null) {
    if (busy.value || loading.value || !ready.value || !saved.value || dirty.value) return
    const ticket = generation
    const context = matterId()
    controller = new AbortController()
    phase.value = 'verifying'
    error.value = ''
    notice.value = ''
    try {
      const current = await readRanking(context, controller.signal)
      if (ticket !== generation) return
      if (!sameRankingVersion(current, saved.value)) {
        ready.value = false
        throw new Error('当前排名版本已变化，请重新读取并核对后再发起自查。')
      }
      phase.value = 'idle'
      await runRecheck(sourceId)
    } catch (cause) {
      if (ticket === generation) {
        error.value = rankingError(cause)
        if (cause instanceof AnalysisNotStartedError)
          notice.value = `排名已保存，尚未重新自查：${cause.message}`
      }
    } finally {
      if (ticket === generation) phase.value = 'idle'
    }
  }

  watch(
    matterId,
    () => {
      generation++
      controller?.abort()
      saved.value = null
      ready.value = false
      loading.value = false
      phase.value = 'idle'
      error.value = ''
      notice.value = ''
      uncertain.value = false
      affected.value = 0
      hydrate()
      void load(true)
    },
    { immediate: true },
  )
  onUnmounted(() => {
    generation++
    controller?.abort()
  })
  return {
    draft,
    saved,
    ready,
    loading,
    phase,
    busy,
    writing,
    dirty,
    error,
    notice,
    uncertain,
    affected,
    load,
    saveAndRecheck,
    recheckSaved,
  }
}
