<script setup lang="ts">
import { computed, onBeforeUnmount } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { ElButton } from 'element-plus'
import type { Matter } from '../matters/types'
import { safeSourceUrl } from '../sources/presentation'
import { canStartAnotherRun, runStatusText } from './contracts'
import { useAnalysis } from './useAnalysis'

const props = defineProps<{
  matter: Matter
  source: {
    id: string
    url: string
    publisher: string
    scope: string | null
    scope_year: number
  } | null
}>()
const emit = defineEmits<{ changed: [] }>()
const analysis = useAnalysis(
  () => props.matter.id,
  () => emit('changed'),
)
const { run, attempt, busy, checking, error, storageReady } = analysis
const canStart = computed(
  () =>
    !busy.value &&
    !checking.value &&
    storageReady.value &&
    props.source !== null &&
    safeSourceUrl(props.source.url) !== null &&
    props.matter.scope_year === props.source.scope_year &&
    canStartAnotherRun(
      run.value?.status ?? (attempt.value?.status === '不可查询' ? null : attempt.value?.status),
    ),
)

async function start() {
  const source = props.source
  if (!source || !canStart.value) return
  if (
    attempt.value &&
    attempt.value.status === null &&
    !window.confirm(
      '上次请求的结果尚未确认，可能仍在执行。重新发起会产生另一批分析，请先核对已保存结果。是否继续？',
    )
  )
    return
  const url = safeSourceUrl(source.url)
  if (!url) return
  await analysis.start(source.id, {
    source_urls: [url],
    publisher: source.publisher,
    scope_year: source.scope_year,
    ...(source.scope ? { scope: source.scope } : {}),
  })
}
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
      此入口暂不提交排名补录内容；补录保存与重新自查待相关接口接齐。分析本身不创建正式任务。
    </p>
    <div class="module-actions">
      <ElButton
        type="primary"
        data-testid="analysis-start"
        :disabled="!canStart"
        :loading="busy"
        @click="start"
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
