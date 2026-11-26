import { onUnmounted, ref } from 'vue'
import { clearAttempt, chooseAttempt, readAttempt, saveAttempt } from './attempt'
import type { Attempt } from './attempt'
import type { Action, Plan, PlanSummary, Task } from './contracts'
import { canConfirmBasis } from './contracts'
import {
  decidePlan,
  decisionMayBeCommitted,
  decisionNeedsReload,
  getPlan,
  getTasks,
  listPlans,
  planError,
} from './api'

export function usePlanReview(onChanged: () => void) {
  const plans = ref<PlanSummary[]>([])
  const plan = ref<Plan | null>(null)
  const tasks = ref<Task[]>([])
  const selectedId = ref('')
  const loading = ref(false)
  const submitting = ref(false)
  const error = ref('')
  const taskError = ref('')
  const decisionError = ref('')
  const notice = ref('')
  const reviewed = ref(false)
  const attempt = ref<Attempt | null>(null)
  const refreshRequired = ref(false)
  let matterId = ''
  let generation = 0
  let controller: AbortController | undefined

  function cancelRead() {
    generation++
    controller?.abort()
    controller = undefined
    loading.value = false
  }

  async function select(planId: string) {
    cancelRead()
    const ticket = generation
    const context = matterId
    const request = new AbortController()
    controller = request
    selectedId.value = planId
    plan.value = null
    tasks.value = []
    reviewed.value = false
    error.value = ''
    taskError.value = ''
    decisionError.value = ''
    notice.value = ''
    attempt.value = null
    loading.value = true
    refreshRequired.value = true
    try {
      const detail = await getPlan(context, planId, request.signal)
      if (ticket !== generation) return
      plan.value = detail
      try {
        if (['confirmed', 'rejected', 'expired'].includes(detail.status)) {
          clearAttempt(context, planId)
        }
        attempt.value = readAttempt(context, planId)
        refreshRequired.value = false
      } catch {
        decisionError.value =
          '无法读取浏览器中的操作标识，当前仅可查看计划。请检查浏览器会话存储后重新读取。'
      }
      if (detail.status === 'confirmed') {
        try {
          const result = await getTasks(context, request.signal)
          if (ticket === generation) tasks.value = result.filter((item) => item.plan_id === planId)
        } catch (cause) {
          if (ticket === generation) taskError.value = planError(cause)
        }
      }
    } catch (cause) {
      if (ticket === generation) {
        error.value = planError(cause)
        plan.value = null
      }
    } finally {
      request.abort()
      if (ticket === generation) {
        loading.value = false
        controller = undefined
      }
    }
  }

  async function load(id: string, linkedId?: string) {
    const preferred = linkedId ?? (matterId === id ? selectedId.value : '')
    cancelRead()
    const ticket = generation
    if (matterId !== id) submitting.value = false
    matterId = id
    plans.value = []
    plan.value = null
    tasks.value = []
    selectedId.value = ''
    attempt.value = null
    reviewed.value = false
    notice.value = ''
    error.value = ''
    taskError.value = ''
    decisionError.value = ''
    refreshRequired.value = true
    loading.value = true
    const request = new AbortController()
    controller = request
    try {
      const result = await listPlans(id, request.signal)
      if (ticket !== generation) return
      plans.value = result
      const selected = result.find((item) => item.id === preferred)
      if (linkedId !== undefined && !selected) {
        error.value = '当前事项中找不到链接指向的候选，请手动选择计划版本。'
        return
      }
      const target = selected ?? result[0]
      if (target) await select(target.id)
    } catch (cause) {
      if (ticket === generation) error.value = planError(cause)
    } finally {
      request.abort()
      if (ticket === generation) {
        loading.value = false
        controller = undefined
      }
    }
  }

  async function decide(action: Action) {
    if (
      !plan.value ||
      plan.value.status !== 'pending' ||
      loading.value ||
      submitting.value ||
      !reviewed.value ||
      refreshRequired.value
    )
      return
    if (action === 'confirm' && !canConfirmBasis(plan.value)) {
      decisionError.value = '个人信息依据已变化，请重新分析并审阅新的候选计划。'
      return
    }
    const currentPlan = plan.value.id
    const context = matterId
    const ticket = generation
    submitting.value = true
    decisionError.value = ''
    notice.value = ''
    let sent = false
    try {
      const operation = chooseAttempt(attempt.value, context, currentPlan, action)
      saveAttempt(operation)
      attempt.value = operation
      sent = true
      const result = await decidePlan(context, currentPlan, action, operation.key)
      clearAttempt(context, currentPlan)
      if (ticket !== generation) return
      attempt.value = null
      const message =
        result.status === 'confirmed'
          ? '确认决定已记录。任务结果以重新读取的列表为准。'
          : '拒绝决定已记录，本次拒绝未创建任务。'
      await load(context)
      if (matterId === context && (selectedId.value === currentPlan || !selectedId.value)) {
        notice.value = message
      }
      if (matterId === context) onChanged()
    } catch (cause) {
      if (ticket !== generation) return
      const message = planError(cause)
      decisionError.value = message
      if (sent && decisionMayBeCommitted(cause)) {
        notice.value =
          '本次决定的结果尚未确认，后端可能已记录。请重新读取状态；重试原决定时将沿用同一操作标识。'
      }
      if (!sent || !decisionMayBeCommitted(cause)) {
        refreshRequired.value = true
        if (sent) {
          try {
            clearAttempt(context, currentPlan)
            attempt.value = null
          } catch {
            decisionError.value = '无法更新浏览器中的操作标识，请先重新读取计划状态。'
            return
          }
        }
      }
      if (decisionNeedsReload(cause)) {
        await load(context, currentPlan)
        if (matterId === context && (selectedId.value === currentPlan || !selectedId.value)) {
          decisionError.value = message
          if (plan.value) onChanged()
        }
      }
    } finally {
      if (matterId === context) submitting.value = false
    }
  }

  function reset() {
    cancelRead()
    matterId = ''
    plans.value = []
    plan.value = null
    tasks.value = []
    selectedId.value = ''
    submitting.value = false
  }
  onUnmounted(reset)
  return {
    plans,
    plan,
    tasks,
    selectedId,
    loading,
    submitting,
    error,
    taskError,
    decisionError,
    notice,
    reviewed,
    attempt,
    refreshRequired,
    load,
    decide,
    reset,
  }
}
