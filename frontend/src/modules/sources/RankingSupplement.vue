<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { ElButton, ElCheckbox, ElInput, ElTag } from 'element-plus'
import { rankingDraftSchema, rankingPercentage } from './rankingDraft'
import type { RankingDraft } from './rankingDraft'
import type { AnalysisRun } from '../analysis/contracts'
import { useRanking } from './useRanking'

const props = defineProps<{
  matterId: string
  sourceId: string | null
  analysisBusy: boolean
  recheckUnavailable: string
  recheck: (sourceId: string | null) => Promise<AnalysisRun | null>
}>()
const emit = defineEmits<{ changed: [] }>()
const ranking = useRanking(
  () => props.matterId,
  () => emit('changed'),
  (sourceId) => props.recheck(sourceId),
  () => props.recheckUnavailable,
)
const {
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
} = ranking
defineExpose({ writing })
const attempted = ref(false)
const validated = computed(() => rankingDraftSchema.safeParse(draft))
const locked = computed(() => loading.value || busy.value || props.analysisBusy)
const missing = computed(() =>
  [
    !draft.rankPosition.trim() ? '本人排名' : '',
    !draft.totalStudents.trim() ? '参与排名总人数' : '',
  ].filter(Boolean),
)
const fieldErrors = computed(() => {
  const errors: Partial<Record<keyof RankingDraft, string>> = {}
  if (attempted.value && !validated.value.success) {
    for (const issue of validated.value.error.issues) {
      const field = issue.path[0] as keyof RankingDraft
      errors[field] ??= issue.message
    }
  }
  return errors
})
const percent = computed(() =>
  validated.value.success
    ? rankingPercentage(validated.value.data.rankPosition, validated.value.data.totalStudents)
    : '',
)

watch(
  () => props.matterId,
  () => {
    attempted.value = false
  },
)
watch(
  () => [draft.rankPosition, draft.totalStudents],
  () => {
    draft.confirmed = false
  },
)

async function checkInput() {
  attempted.value = true
  await nextTick()
  const field = (['rankPosition', 'totalStudents', 'confirmed'] as const).find(
    (key) => fieldErrors.value[key],
  )
  if (field) document.getElementById(`ranking-${field}`)?.focus()
}

async function submitRanking() {
  if (locked.value || !ready.value) return
  const sourceId = props.sourceId
  await checkInput()
  if (validated.value.success) await ranking.saveAndRecheck(sourceId)
}

function reloadRanking() {
  void ranking.load(!dirty.value)
}

function canLeave() {
  return (
    !(dirty.value || writing.value || uncertain.value) ||
    window.confirm(
      '排名有未保存输入或尚未核对的保存请求。离开不会撤销已提交请求，返回后请重新读取核对。是否离开？',
    )
  )
}
onBeforeRouteLeave(canLeave)
onBeforeRouteUpdate((to, from) => (to.params.matterId === from.params.matterId ? true : canLeave()))
function preventClose(event: BeforeUnloadEvent) {
  if (!(dirty.value || writing.value || uncertain.value)) return
  event.preventDefault()
  event.returnValue = ''
}
window.addEventListener('beforeunload', preventClose)
onBeforeUnmount(() => window.removeEventListener('beforeunload', preventClose))
</script>

<template>
  <section
    class="panel ranking-supplement"
    aria-labelledby="ranking-heading"
    data-testid="ranking-panel"
    :aria-busy="loading || busy"
  >
    <div class="section-heading">
      <h2 id="ranking-heading">补充本人排名信息</h2>
      <ElTag :type="ready && saved && !dirty ? 'success' : 'warning'">
        {{
          !ready
            ? '需读取核对'
            : dirty
              ? '有未保存修改'
              : saved
                ? `已保存 v${saved.version_no}`
                : '未保存'
        }}
      </ElTag>
    </div>
    <p class="muted">仅供本人当前事项使用，不共享；信息由本人确认，不代表官方核实。</p>
    <p v-if="missing.length" class="muted" role="status">待补充：{{ missing.join('、') }}。</p>
    <div class="module-actions">
      <ElButton
        data-testid="ranking-refresh"
        :disabled="locked"
        :loading="loading"
        @click="reloadRanking"
        >重新读取排名</ElButton
      >
    </div>
    <p v-if="loading" role="status">正在读取当前事项的排名…</p>
    <p
      v-if="saved"
      class="muted"
      data-testid="ranking-saved"
      :data-fact-id="saved.id"
      :data-version="saved.version_no"
      :data-matter-id="saved.matter_id"
    >
      最近读取／保存记录：{{ saved.value_text }}，百分位 {{ saved.value.percentile }}%，版本 v{{
        saved.version_no
      }}。
      {{ saved.scope ? `统计范围：${saved.scope}。` : '' }}
      {{ saved.valid_from ? `生效日期：${saved.valid_from}。` : '' }}
      {{
        saved.value.position === null
          ? '当前记录仅提供百分位；如需替换，请填写真实名次和总人数。'
          : ''
      }}
    </p>
    <p v-if="error" role="alert" class="error-text" data-testid="ranking-error">{{ error }}</p>
    <p v-if="notice" role="status" data-testid="ranking-notice">{{ notice }}</p>
    <p v-if="affected" class="muted">
      当前事项有 {{ affected }} 个候选涉及旧排名依据，需重新分析并审阅；实际状态以重新读取为准。
    </p>
    <form class="ranking-form" novalidate @submit.prevent="submitRanking">
      <div>
        <label for="ranking-rankPosition">本人排名</label>
        <ElInput
          id="ranking-rankPosition"
          v-model="draft.rankPosition"
          :disabled="locked || !ready"
          inputmode="numeric"
          autocomplete="off"
          placeholder="填写正整数"
          :aria-invalid="Boolean(fieldErrors.rankPosition)"
          :aria-describedby="fieldErrors.rankPosition ? 'ranking-position-error' : undefined"
        />
        <p
          v-if="fieldErrors.rankPosition"
          id="ranking-position-error"
          class="error-text"
          role="alert"
        >
          {{ fieldErrors.rankPosition }}
        </p>
      </div>
      <div>
        <label for="ranking-totalStudents">参与排名总人数</label>
        <ElInput
          id="ranking-totalStudents"
          v-model="draft.totalStudents"
          :disabled="locked || !ready"
          inputmode="numeric"
          autocomplete="off"
          placeholder="与本人排名采用同一统计范围"
          :aria-invalid="Boolean(fieldErrors.totalStudents)"
          :aria-describedby="fieldErrors.totalStudents ? 'ranking-total-error' : undefined"
        />
        <p
          v-if="fieldErrors.totalStudents"
          id="ranking-total-error"
          class="error-text"
          role="alert"
        >
          {{ fieldErrors.totalStudents }}
        </p>
      </div>
      <div class="ranking-confirmation">
        <ElCheckbox
          id="ranking-confirmed"
          v-model="draft.confirmed"
          :disabled="locked || !ready"
          :aria-describedby="fieldErrors.confirmed ? 'ranking-confirmation-error' : undefined"
        >
          我已核对这两项信息采用同一统计范围，并确认填写内容真实。
        </ElCheckbox>
        <p
          v-if="fieldErrors.confirmed"
          id="ranking-confirmation-error"
          class="error-text"
          role="alert"
        >
          {{ fieldErrors.confirmed }}
        </p>
      </div>
      <div class="module-actions ranking-confirmation">
        <ElButton :disabled="locked || !ready" @click="checkInput">检查输入</ElButton>
        <ElButton
          native-type="submit"
          data-testid="ranking-save"
          type="primary"
          :loading="busy"
          :disabled="locked || !ready"
        >
          {{ recheckUnavailable ? '保存排名' : '保存并重新自查' }}
        </ElButton>
        <ElButton
          data-testid="ranking-recheck"
          :disabled="locked || !ready || !saved || dirty || Boolean(recheckUnavailable)"
          @click="ranking.recheckSaved(sourceId)"
          >仅重新自查</ElButton
        >
      </div>
    </form>
    <p v-if="attempted && validated.success" role="status">
      本地输入检查通过{{ dirty || !saved ? '，尚未保存' : '' }}。排名比例：{{
        draft.rankPosition.trim()
      }}
      ÷ {{ draft.totalStudents.trim() }} = {{ percent }}。
    </p>
    <p class="muted">
      排名比例仅用于展示，不据此判断是否符合申请条件。保存成功后才会参与当前事项的重新自查；未保存输入刷新后无法恢复。
    </p>
    <p v-if="recheckUnavailable && !busy" class="muted">
      暂不能重新自查：{{ recheckUnavailable }} 已保存的排名可稍后重试自查。
    </p>
    <p v-if="phase === 'verifying'" role="status">正在核对后端排名版本…</p>
    <p v-if="phase === 'rechecking'" role="status">排名已保存，正在等待重新自查反馈…</p>
  </section>
</template>
