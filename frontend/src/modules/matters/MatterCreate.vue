<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, reactive, ref } from 'vue'
import { onBeforeRouteLeave, useRouter } from 'vue-router'
import { useWorkspace } from '../../app/useWorkspace'
import { matterPath } from '../../router/paths'
import { createMatterSchema } from './types'
import { describeFailure } from './errors'

const router = useRouter()
const { mattersApi } = useWorkspace()
const form = reactive({ goal: '', scope_year: '' })
const fieldErrors = ref<Record<string, string>>({})
const errorCount = computed(() => Object.keys(fieldErrors.value).length)
const saving = ref(false)
const uncertain = ref(false)
const failure = ref('')
let mounted = true
let saved = false
const dirty = computed(() => Boolean(form.goal || form.scope_year))

function preventClose(event: BeforeUnloadEvent) {
  if (saving.value || (dirty.value && !saved)) {
    event.preventDefault()
    event.returnValue = ''
  }
}
window.addEventListener('beforeunload', preventClose)
onBeforeUnmount(() => {
  mounted = false
  window.removeEventListener('beforeunload', preventClose)
})
onBeforeRouteLeave(() => {
  if (saved) return true
  if (saving.value) return false
  return (
    !dirty.value ||
    window.confirm(
      uncertain.value
        ? '创建结果尚未确认。离开后请先在事项列表核对，避免重复创建。是否离开？'
        : '表单尚未保存，离开后需要重新填写。是否离开？',
    )
  )
})

async function submit() {
  if (saving.value || uncertain.value) return
  failure.value = ''
  fieldErrors.value = {}
  const input = createMatterSchema.safeParse({
    goal: form.goal,
    type_code: 'pre_recommend',
    scope_year: form.scope_year.trim() ? Number(form.scope_year) : Number.NaN,
    scope_attrs: {},
  })
  if (!input.success) {
    for (const issue of input.error.issues) {
      fieldErrors.value[String(issue.path[0])] =
        issue.path[0] === 'scope_year' ? '请填写 2020—2100 之间的整数年度' : issue.message
    }
    if (!form.goal.trim()) fieldErrors.value.goal = '请输入工作区名称'
    await nextTick()
    document.getElementById(fieldErrors.value.goal ? 'matter-goal' : 'scope-year')?.focus()
    return
  }
  if (!mattersApi) {
    failure.value = '事项服务尚未连接，当前内容尚未保存。请保留表单，连接后再提交。'
    return
  }
  saving.value = true
  try {
    const created = await mattersApi.create(input.data)
    if (!mounted) return
    saved = true
    await router.push(matterPath(created.id))
  } catch (error) {
    if (!mounted) return
    const result = describeFailure(error, true)
    uncertain.value = result.uncertain
    failure.value = result.message
  } finally {
    if (mounted) saving.value = false
  }
}
</script>

<template>
  <section class="page create-workspace">
    <div class="page-header">
      <div>
        <h1>新建工作区</h1>
        <p class="muted">填写事项的基本信息。官方来源可在创建后补充。</p>
      </div>
    </div>
    <div v-if="errorCount" class="create-feedback create-feedback-error" role="alert">
      <strong>有 {{ errorCount }} 项必填信息需要核对，尚未创建</strong>
      <p>请检查工作区名称和适用年度。</p>
    </div>
    <div v-else-if="failure" class="create-feedback create-feedback-error" role="alert">
      <strong>{{ uncertain ? '创建结果尚未确认' : '无法创建工作区' }}</strong>
      <p>{{ failure }}</p>
    </div>
    <div v-else-if="!mattersApi" class="create-feedback" role="status">
      事项服务尚未连接。可以填写和检查表单，暂时无法保存。
    </div>
    <div class="create-columns">
      <el-form
        class="card create-form"
        label-position="top"
        require-asterisk-position="right"
        :model="form"
        aria-labelledby="create-details"
        @submit.prevent="submit"
      >
        <h2 id="create-details">01 填写基本信息</h2>
        <el-form-item label="工作区名称" for="matter-goal" required :error="fieldErrors.goal">
          <el-input
            id="matter-goal"
            v-model="form.goal"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 3 }"
            maxlength="200"
            placeholder="请输入工作区名称"
            aria-label="工作区名称"
            aria-required="true"
            :aria-invalid="Boolean(fieldErrors.goal)"
            :disabled="saving || uncertain"
          />
        </el-form-item>
        <el-form-item label="事项类型" for="matter-type" required>
          <el-input id="matter-type" model-value="推免" readonly aria-label="事项类型" />
        </el-form-item>
        <div class="create-field-row">
          <el-form-item label="适用年度" for="scope-year" required :error="fieldErrors.scope_year">
            <el-input
              id="scope-year"
              v-model="form.scope_year"
              inputmode="numeric"
              maxlength="4"
              placeholder="请输入适用年度"
              aria-label="适用年度"
              aria-required="true"
              :aria-invalid="Boolean(fieldErrors.scope_year)"
              :disabled="saving || uncertain"
            />
          </el-form-item>
        </div>
        <h2>02 添加来源</h2>
        <div class="create-source">
          <strong>创建后核对官方通知</strong>
          <p>在工作区的「来源与条件」中查看通知出处和适用范围。</p>
        </div>
        <div class="form-actions create-actions">
          <el-button
            type="primary"
            native-type="submit"
            :loading="saving"
            :disabled="saving || uncertain"
          >
            {{ saving ? '正在保存' : '创建工作区' }}
          </el-button>
          <RouterLink class="secondary-link" to="/matters">
            {{ uncertain ? '去事项列表核对结果' : '取消' }}
          </RouterLink>
        </div>
      </el-form>
      <aside class="card create-guide" aria-labelledby="create-guide-title">
        <h2 id="create-guide-title">一个事项，一个清晰的空间</h2>
        <dl>
          <div>
            <dt>01 核对来源与条件</dt>
            <dd>查看官方通知中的资格条件、材料清单和截止日期，保留出处。</dd>
          </div>
          <div>
            <dt>02 审阅候选计划</dt>
            <dd>查看候选任务和依据。确认计划后，任务才会进入个人工作区。</dd>
          </div>
          <div>
            <dt>03 准备材料与归档</dt>
            <dd>按官方要求准备材料，并由本人在官方入口完成提交。</dd>
          </div>
        </dl>
      </aside>
    </div>
  </section>
</template>

<style scoped>
.create-columns {
  display: grid;
  grid-template-columns: minmax(0, 1.62fr) minmax(0, 1fr);
  align-items: start;
  gap: 24px;
}

.create-form,
.create-guide {
  padding: 24px;
  border-color: #e5e0f0;
  border-radius: 14px;
}

.create-form h2,
.create-guide h2 {
  margin: 0 0 18px;
  font-size: 20px;
  font-weight: 700;
  line-height: 1.4;
}

.create-form :deep(.el-form-item) {
  margin-bottom: 16px;
}

.create-form :deep(.el-form-item__label) {
  height: auto;
  margin-bottom: 6px;
  color: var(--page2-ink, #25243d);
  font-size: 15px;
  font-weight: 700;
  line-height: 1.5;
}

.create-form :deep(.el-input__wrapper),
.create-form :deep(.el-textarea__inner) {
  min-height: 48px;
  border-radius: 8px;
  background: var(--page2-bg, #f7f8fb);
  box-shadow: 0 0 0 1px #e5e0f0 inset;
  font-size: 15px;
}

.create-form :deep(.el-input__wrapper) {
  padding-inline: 16px;
}

.create-form :deep(.el-textarea__inner) {
  padding: 12px 16px;
  line-height: 24px;
  resize: none;
}

.create-form :deep(.el-textarea__inner:focus),
.create-form :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 2px var(--page2-brand, #30246d) inset;
}

.create-form :deep(.el-input__inner::placeholder),
.create-form :deep(.el-textarea__inner::placeholder) {
  color: #706684;
}

.create-form :deep(.is-error .el-input__wrapper),
.create-form :deep(.is-error .el-textarea__inner) {
  box-shadow: 0 0 0 1px #b33446 inset;
}

.create-form :deep(.is-error .el-input__wrapper.is-focus),
.create-form :deep(.is-error .el-textarea__inner:focus) {
  box-shadow: 0 0 0 2px #b33446 inset;
}

.create-form :deep(.el-form-item__error) {
  position: static;
  width: 100%;
  padding-top: 6px;
  color: #a7293d;
  font-size: 14px;
  line-height: 1.4;
}

.create-field-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.create-source,
.create-feedback {
  padding: 14px 20px;
  border: 1px solid var(--page2-line, #e9e5f0);
  border-radius: 13px;
  background: var(--page2-lavender, #eeeaf8);
  color: var(--page2-brand, #30246d);
}

.create-source {
  padding-block: 18px;
  border-radius: 8px;
}

.create-feedback {
  margin-bottom: 16px;
}

.create-source p,
.create-feedback p {
  margin: 4px 0 0;
  color: var(--page2-muted, #656176);
  font-size: 14px;
  line-height: 1.5;
}

.create-feedback-error {
  border-color: #f1dce0;
  background: #fbedef;
  color: #ad4252;
}

.create-actions {
  gap: 12px;
  margin-top: 16px;
}

.create-actions :deep(.el-button) {
  min-height: 44px;
  border-radius: 8px;
  padding-inline: 18px;
  font-size: 15px;
  font-weight: 700;
}

.create-guide dl {
  display: grid;
  grid-template-columns: 1fr;
  gap: 16px;
  margin: 0;
}

.create-guide dt {
  color: var(--page2-brand, #30246d);
  font-size: 16px;
  font-weight: 700;
}

.create-guide dd {
  margin: 8px 0 0;
  color: var(--page2-muted, #656176);
  font-size: 15px;
  line-height: 1.6;
}

@media (max-width: 1020px) {
  .create-columns {
    gap: 16px;
  }

  .create-field-row {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 880px) {
  .create-columns {
    grid-template-columns: 1fr;
  }
}
</style>
