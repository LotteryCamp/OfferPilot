<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { ElButton, ElCheckbox, ElInput, ElTag } from 'element-plus'
import { rankingDraftSchema, rankingPercentage } from './rankingDraft'
import type { RankingDraft } from './rankingDraft'

const props = defineProps<{ matterId: string }>()
const draft = reactive<RankingDraft>({ rankPosition: '', totalStudents: '', confirmed: false })
const attempted = ref(false)
const validated = computed(() => rankingDraftSchema.safeParse(draft))
const dirty = computed(() => Boolean(draft.rankPosition || draft.totalStudents || draft.confirmed))
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
    draft.rankPosition = ''
    draft.totalStudents = ''
    draft.confirmed = false
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

function canLeave() {
  return !dirty.value || window.confirm('当前排名输入尚未保存，离开后需要重新填写。是否离开？')
}
onBeforeRouteLeave(canLeave)
onBeforeRouteUpdate((to, from) => (to.params.matterId === from.params.matterId ? true : canLeave()))
function preventClose(event: BeforeUnloadEvent) {
  if (!dirty.value) return
  event.preventDefault()
  event.returnValue = ''
}
window.addEventListener('beforeunload', preventClose)
onBeforeUnmount(() => window.removeEventListener('beforeunload', preventClose))
</script>

<template>
  <section class="panel ranking-supplement" aria-labelledby="ranking-heading">
    <div class="section-heading">
      <h2 id="ranking-heading">补充本人排名信息</h2>
      <ElTag type="warning">未保存</ElTag>
    </div>
    <p class="muted">仅供本人当前事项使用，不共享；信息由本人确认，不代表官方核实。</p>
    <p v-if="missing.length" class="muted" role="status">待补充：{{ missing.join('、') }}。</p>
    <form class="ranking-form" novalidate @submit.prevent="checkInput">
      <div>
        <label for="ranking-rankPosition">本人排名</label>
        <ElInput
          id="ranking-rankPosition"
          v-model="draft.rankPosition"
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
        <ElButton native-type="submit">检查输入</ElButton>
        <ElButton type="primary" disabled>保存并重新自查（尚未接通）</ElButton>
      </div>
    </form>
    <p v-if="attempted && validated.success" role="status">
      本地输入检查通过，尚未保存。排名比例：{{ draft.rankPosition.trim() }} ÷
      {{ draft.totalStudents.trim() }} = {{ percent }}。
    </p>
    <p class="muted">
      排名比例仅用于展示，不据此判断是否符合申请条件。保存和重新自查服务尚未接通，当前输入仅保留在本页，刷新后无法恢复。
    </p>
  </section>
</template>
