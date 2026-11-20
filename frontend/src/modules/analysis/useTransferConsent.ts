import { computed, onUnmounted, ref, watch } from 'vue'
import type { Matter } from '../matters/types'
import {
  consentError,
  grantTransferConsent,
  readTransferConsent,
  revokeTransferConsent,
} from './consentApi'
import { consentBlockReason, consentMatches, sameDisclosure } from './consentContracts'
import type { TransferConsentState } from './consentContracts'

export function useTransferConsent(matter: () => Matter) {
  const state = ref<TransferConsentState | null>(null)
  const busy = ref(false)
  const accepted = ref(false)
  const error = ref('')
  const notice = ref('')
  const pendingRevokeId = ref<string | null>(null)
  const blockedReason = computed(() => {
    if (busy.value) return '正在核对模型传输授权，请稍候。'
    if (pendingRevokeId.value) return '撤回结果尚需核对，请重新读取或重试撤回。'
    return consentBlockReason(state.value, matter().id)
  })
  let generation = 0
  let controller: AbortController | undefined

  function reconcile(value: TransferConsentState) {
    if (pendingRevokeId.value && value.consent?.consent_id === pendingRevokeId.value) {
      state.value = null
      throw new Error('该授权仍处于有效状态；如仍需撤回，请重试撤回。')
    }
    pendingRevokeId.value = null
    state.value = value
    accepted.value = false
    return value
  }

  async function refresh() {
    if (busy.value) return null
    const ticket = generation
    const context = matter().id
    controller = new AbortController()
    busy.value = true
    error.value = ''
    notice.value = ''
    try {
      const value = await readTransferConsent(context, controller.signal)
      if (ticket !== generation) return null
      return reconcile(value)
    } catch (cause) {
      if (ticket === generation) {
        state.value = null
        accepted.value = false
        error.value = consentError(cause)
      }
      return null
    } finally {
      if (ticket === generation) busy.value = false
    }
  }

  async function grant() {
    if (
      busy.value ||
      !accepted.value ||
      !state.value ||
      state.value.consent ||
      pendingRevokeId.value
    )
      return
    const disclosed = state.value.disclosure
    const context = matter().id
    const ticket = generation
    controller = new AbortController()
    const signal = controller.signal
    busy.value = true
    error.value = ''
    notice.value = ''
    try {
      const latest = await readTransferConsent(context, signal)
      if (ticket !== generation) return
      if (!sameDisclosure(disclosed, latest.disclosure)) {
        state.value = latest
        accepted.value = false
        notice.value = '披露内容已更新，请重新阅读并确认。'
        return
      }
      if (latest.consent) {
        reconcile(latest)
        notice.value = '已读取当前事项的既有授权，请核对其范围。'
        return
      }
      const granted = await grantTransferConsent(context, signal)
      if (ticket !== generation) return
      state.value = null
      const verified = await readTransferConsent(context, signal)
      if (ticket !== generation) return
      if (
        !sameDisclosure(disclosed, verified.disclosure) ||
        verified.consent?.consent_id !== granted.consent_id ||
        !consentMatches(granted, verified.disclosure, context)
      )
        throw new Error('授予后授权或披露信息发生变化，请重新读取核对。')
      reconcile(verified)
      notice.value = '当前事项的授权已记录，可主动发起分析或重新自查。'
    } catch (cause) {
      if (ticket === generation) {
        state.value = null
        accepted.value = false
        error.value = consentError(cause)
        notice.value = '本次操作结果需重新读取核对，尚未自动发起分析。'
      }
    } finally {
      if (ticket === generation) busy.value = false
    }
  }

  async function revoke() {
    const id = pendingRevokeId.value ?? state.value?.consent?.consent_id
    if (!id || busy.value) return
    const context = matter().id
    const ticket = generation
    controller = new AbortController()
    const signal = controller.signal
    pendingRevokeId.value = id
    state.value = null
    accepted.value = false
    busy.value = true
    error.value = ''
    notice.value = ''
    try {
      await revokeTransferConsent(context, id, signal)
      if (ticket !== generation) return
      const verified = await readTransferConsent(context, signal)
      if (ticket !== generation) return
      reconcile(verified)
      notice.value = verified.consent
        ? '原授权已撤回；当前存在另一条授权，请重新核对。'
        : '授权已撤回，旧标识已停止使用；再次需要授权时须由本人重新确认。'
    } catch (cause) {
      if (ticket === generation) {
        error.value = consentError(cause)
        notice.value = '已停止使用旧标识，撤回结果请重新读取核对；若仍有效，可重试撤回。'
      }
    } finally {
      if (ticket === generation) busy.value = false
    }
  }

  watch(
    [() => matter().id, () => JSON.stringify(matter().scope_attrs ?? {})],
    (value, previous) => {
      generation++
      controller?.abort()
      state.value = null
      busy.value = false
      accepted.value = false
      if (value[0] !== previous?.[0]) pendingRevokeId.value = null
      error.value = ''
      notice.value = ''
      void refresh()
    },
    { immediate: true },
  )
  onUnmounted(() => {
    generation++
    controller?.abort()
  })
  return {
    state,
    busy,
    accepted,
    error,
    notice,
    pendingRevokeId,
    blockedReason,
    refresh,
    grant,
    revoke,
  }
}
