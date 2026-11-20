<script setup lang="ts">
import { computed, onBeforeUnmount } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { ElButton, ElCheckbox } from 'element-plus'
import type { Matter } from '../matters/types'
import { safeSourceUrl } from '../sources/presentation'
import { canStartAnotherRun, runStatusText } from './contracts'
import { useAnalysis } from './useAnalysis'
import { useTransferConsent } from './useTransferConsent'
import { consentBlockReason, transferScopeLabel } from './consentContracts'

const props = defineProps<{
  matter: Matter
  source: {
    id: string
    url: string
    publisher: string
    scope: string | null
    scope_year: number
  } | null
  rankingSaving: boolean
}>()
const emit = defineEmits<{ changed: [] }>()
const analysis = useAnalysis(
  () => props.matter.id,
  () => emit('changed'),
)
const { run, attempt, busy, checking, error, storageReady } = analysis
const transfer = useTransferConsent(() => props.matter)
const {
  state: consentState,
  busy: consentBusy,
  accepted: consentAccepted,
  error: transferError,
  notice: transferNotice,
  pendingRevokeId,
} = transfer
const canStart = computed(
  () =>
    !busy.value &&
    !props.rankingSaving &&
    !checking.value &&
    storageReady.value &&
    props.source !== null &&
    safeSourceUrl(props.source.url) !== null &&
    props.matter.scope_year === props.source.scope_year &&
    canStartAnotherRun(
      run.value?.status ?? (attempt.value?.status === '不可查询' ? null : attempt.value?.status),
    ),
)
const blockedReason = computed(() => {
  if (props.rankingSaving) return '排名正在保存和核对，请稍后重试。'
  if (busy.value || checking.value) return '分析正在执行或查询，请等待当前操作结束。'
  if (!storageReady.value) return '浏览器无法保存运行标识，请先检查会话存储。'
  if (!props.source || !safeSourceUrl(props.source.url)) return '请先选择可分析的公开来源。'
  if (props.matter.scope_year !== props.source.scope_year) return '来源与事项的适用年度不一致。'
  if (transfer.blockedReason.value) return transfer.blockedReason.value
  if (!canStart.value) return '请先核对当前运行状态，再重新发起。'
  return ''
})

async function start(expectedSourceId?: string) {
  const source = props.source
  if (!source || blockedReason.value || (expectedSourceId && source.id !== expectedSourceId))
    return null
  if (
    attempt.value &&
    attempt.value.status === null &&
    !window.confirm(
      '上次请求的结果尚未确认，可能仍在执行。重新发起会产生另一批分析，请先核对已保存结果。是否继续？',
    )
  )
    return null
  const url = safeSourceUrl(source.url)
  if (!url) return null
  const context = props.matter.id
  const currentConsent = await transfer.refresh()
  if (
    !currentConsent ||
    props.matter.id !== context ||
    props.source?.id !== source.id ||
    consentBlockReason(currentConsent, context)
  )
    return null
  const result = await analysis.start(source.id, {
    source_urls: [url],
    publisher: source.publisher,
    scope_year: source.scope_year,
    ...(source.scope ? { scope: source.scope } : {}),
    ...(currentConsent.consent
      ? { model_transfer_consent_id: currentConsent.consent.consent_id }
      : {}),
  })
  if (!result && props.matter.id === context) await transfer.refresh()
  return result
}
defineExpose({
  start,
  busy: computed(() => busy.value || checking.value || consentBusy.value),
  blockedReason,
})
function canLeave() {
  return (
    !busy.value ||
    window.confirm('分析请求正在等待返回。离开不会停止后台运行，结果需重新核对。是否离开？')
  )
}
onBeforeRouteLeave(canLeave)
onBeforeRouteUpdate((to, from) => to.params.matterId === from.params.matterId || canLeave())
function preventClose(event: BeforeUnloadEvent) {
  if (!busy.value) return
  event.preventDefault()
  event.returnValue = ''
}
window.addEventListener('beforeunload', preventClose)
onBeforeUnmount(() => window.removeEventListener('beforeunload', preventClose))
</script>

<template>
  <section class="panel analysis-panel" data-testid="analysis-panel" :aria-busy="busy || checking">
    <h2>分析公开来源</h2>
    <p v-if="source">
      当前选择：{{ source.publisher }}。开始后重新读取该公开网页，提取要求并生成候选计划。
    </p>
    <p v-else class="muted">请先读取公开通知，或在关联来源中选择要分析的来源。</p>
    <p class="muted">
      分析使用后端已保存的当前事项事实，未保存的排名输入不参与自查。分析本身不创建正式任务。
    </p>
    <section class="evidence-block" data-testid="analysis-consent" :aria-busy="consentBusy">
      <div class="section-heading">
        <h3>模型传输授权</h3>
        <ElButton
          data-testid="consent-refresh"
          :disabled="consentBusy"
          :loading="consentBusy"
          @click="transfer.refresh"
          >读取授权状态</ElButton
        >
      </div>
      <p v-if="transferError" role="alert" class="error-text" data-testid="consent-error">
        {{ transferError }}
      </p>
      <p v-if="transferNotice" role="status" data-testid="consent-notice">{{ transferNotice }}</p>
      <template v-if="consentState">
        <dl class="metadata-grid" data-testid="consent-disclosure">
          <div>
            <dt>服务商</dt>
            <dd>{{ consentState.disclosure.provider }}</dd>
          </div>
          <div>
            <dt>模型名称</dt>
            <dd>{{ consentState.disclosure.model || '服务端尚未提供' }}</dd>
          </div>
          <div class="wide">
            <dt>用途</dt>
            <dd>{{ consentState.disclosure.purposes.map(transferScopeLabel).join('、') }}</dd>
          </div>
          <div class="wide">
            <dt>发送字段</dt>
            <dd>
              {{ consentState.disclosure.field_categories.map(transferScopeLabel).join('、') }}
            </dd>
          </div>
          <div class="wide">
            <dt>数据处理说明</dt>
            <dd>{{ consentState.disclosure.data_handling }}</dd>
          </div>
        </dl>
        <p
          v-if="consentState.consent"
          data-testid="consent-active"
          :data-consent-id="consentState.consent.consent_id"
          :data-matter-id="consentState.consent.matter_id"
        >
          本事项已有授权记录 v{{ consentState.consent.version_no }}，服务商为
          {{ consentState.consent.provider }}。
        </p>
        <template v-else-if="consentState.required">
          <ElCheckbox id="consent-confirmed" v-model="consentAccepted" :disabled="consentBusy"
            >我已阅读以上服务商、用途、发送字段及数据处理说明，同意本事项按上述范围进行模型传输。</ElCheckbox
          >
          <ElButton
            data-testid="consent-grant"
            :disabled="consentBusy || !consentAccepted"
            @click="transfer.grant"
            >同意并授权本事项分析</ElButton
          >
        </template>
        <p v-else class="muted">按当前后端状态，本次公开资料分析无需额外授权。</p>
      </template>
      <ElButton
        v-if="consentState?.consent || pendingRevokeId"
        data-testid="consent-revoke"
        :disabled="consentBusy"
        @click="transfer.revoke"
        >{{ pendingRevokeId ? '重试撤回授权' : '撤回本事项授权' }}</ElButton
      >
      <p class="muted">撤回影响后续调用检查；已发出的请求由模型服务按其数据处理条款处理。</p>
    </section>
    <div class="module-actions">
      <ElButton
        type="primary"
        data-testid="analysis-start"
        :disabled="Boolean(blockedReason)"
        :loading="busy"
        @click="start()"
      >
        {{ attempt ? '重新发起分析' : '开始分析' }}
      </ElButton>
      <ElButton
        data-testid="analysis-status-refresh"
        :disabled="!attempt?.runId || busy || checking"
        :loading="checking"
        @click="analysis.check"
        >查询运行状态</ElButton
      >
      <ElButton data-testid="analysis-results-refresh" :disabled="busy" @click="emit('changed')"
        >刷新已保存结果</ElButton
      >
      <RouterLink
        :to="{ name: 'matter-plan', params: { matterId: matter.id } }"
        class="secondary-link"
        >查看候选计划 →</RouterLink
      >
    </div>
    <p v-if="blockedReason && !busy && !checking" class="muted">{{ blockedReason }}</p>
    <p v-if="busy" role="status">正在等待分析返回，请勿重复提交。离开页面不会停止后台运行。</p>
    <p v-if="error" class="error-text" role="alert" data-testid="analysis-error">{{ error }}</p>
    <section
      v-if="run"
      data-testid="analysis-result"
      :data-run-id="run.run_id"
      :data-run-status="run.status"
      :data-source-id="attempt?.sourceId"
    >
      <h3>最近一次分析反馈</h3>
      <p role="status">{{ runStatusText(run) }}</p>
      <p v-if="run.error" class="error-text">{{ run.error.message }}（{{ run.error.code }}）</p>
      <p v-if="run.error?.missing_fields.length" class="muted">
        待补充或核对：{{ run.error.missing_fields.join('、') }}
      </p>
    </section>
  </section>
</template>
