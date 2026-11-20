<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import axios from 'axios'
import { z } from 'zod'
import { ElButton, ElInput } from 'element-plus'
import type { Matter } from '../matters/types'
import type { SourceReadResult } from './contracts'
import { readPublicSource } from './api'
import { displayDate, safeSourceUrl } from './presentation'

const props = defineProps<{ matter: Matter; analyzedSnapshots: ReadonlySet<string> }>()
const emit = defineEmits<{ read: [result: SourceReadResult] }>()
const url = ref('')
const publisher = ref('')
const scope = ref('')
const submitting = ref(false)
const error = ref('')
const result = ref<SourceReadResult | null>(null)
const hasAnalysis = computed(
  () =>
    result.value !== null &&
    props.analyzedSnapshots.has(`${result.value.source.id}/${result.value.snapshot.id}`),
)
let request: AbortController | undefined
let sequence = 0

function reset() {
  sequence++
  request?.abort()
  request = undefined
  url.value = ''
  publisher.value = ''
  scope.value = ''
  error.value = ''
  result.value = null
  submitting.value = false
}
watch(() => props.matter.id, reset)
onUnmounted(reset)

async function submit() {
  if (submitting.value) return
  error.value = ''
  const target = safeSourceUrl(url.value.trim())
  if (!target || target.length > 500) {
    error.value = '请填写不含账号密码的有效 HTTP 或 HTTPS 来源链接，最多 500 字符。'
    return
  }
  const author = publisher.value.trim()
  if (!author || author.length > 160 || scope.value.trim().length > 200) {
    error.value = '请填写发布单位（最多 160 字符），适用范围最多 200 字符。'
    return
  }
  const year = props.matter.scope_year
  if (year === null || year < 2020 || year > 2100) {
    error.value = '当前事项缺少有效的适用年度，请先核对事项信息。'
    return
  }
  const current = ++sequence
  request = new AbortController()
  submitting.value = true
  result.value = null
  try {
    const data = await readPublicSource(
      props.matter.id,
      { url: target, publisher: author, scope_year: year, scope: scope.value.trim() || undefined },
      request.signal,
    )
    if (current !== sequence) return
    result.value = data
    emit('read', data)
  } catch (cause) {
    if (current !== sequence) return
    if (axios.isAxiosError(cause)) {
      const body = z
        .object({
          error: z.object({ code: z.string(), message: z.string(), next: z.string().optional() }),
        })
        .safeParse(cause.response?.data)
      const status = cause.response?.status
      error.value =
        status && body.success && (status < 500 || body.data.error.code === 'source_read_failed')
          ? [body.data.error.message, body.data.error.next].filter(Boolean).join('；')
          : '来源读取结果暂未确认，请稍后核对或重新读取。'
    } else {
      error.value = '来源返回的内容不符合约定，请核对后端响应后重新读取。'
    }
  } finally {
    if (current === sequence) {
      request = undefined
      submitting.value = false
    }
  }
}
</script>

<template>
  <details class="panel source-import" data-testid="source-import">
    <summary>读取公开通知</summary>
    <p class="muted">
      支持公开 HTML 通知页面。读取后可查看原文及出处，相关要求生成后会出现在来源列表。
    </p>
    <form class="source-import-form" :aria-busy="submitting" @submit.prevent="submit">
      <label for="source-url">通知链接</label>
      <ElInput
        id="source-url"
        v-model="url"
        :disabled="submitting"
        maxlength="500"
        placeholder="https://…"
      />
      <label for="source-publisher">发布单位</label>
      <ElInput
        id="source-publisher"
        v-model="publisher"
        :disabled="submitting"
        maxlength="160"
        placeholder="填写通知发布单位"
      />
      <label for="source-scope">适用范围（选填）</label>
      <ElInput
        id="source-scope"
        v-model="scope"
        :disabled="submitting"
        maxlength="200"
        placeholder="例如学院、适用对象或批次"
      />
      <p class="muted">适用年度：{{ matter.scope_year ?? '未填写，暂时无法读取来源' }}</p>
      <p v-if="error" class="error-text" role="alert">{{ error }}</p>
      <ElButton
        data-testid="source-read-submit"
        native-type="submit"
        type="primary"
        :loading="submitting"
        :disabled="matter.scope_year === null"
        >读取通知</ElButton
      >
    </form>
    <section
      v-if="result"
      class="import-result"
      aria-label="本次来源读取结果"
      data-testid="source-read-result"
      :data-source-id="result.source.id"
      :data-snapshot-id="result.snapshot.id"
    >
      <p role="status">
        <strong>{{ hasAnalysis ? '已读取通知' : '已读取，待分析' }}</strong> · 快照 v{{
          result.snapshot.version_no
        }}
      </p>
      <p v-if="!hasAnalysis" class="muted">
        关联列表尚未返回本快照的要求。原文读取已完成，分析与自查结果需后续生成。
      </p>
      <h3>{{ result.snapshot.title || '来源未提供标题' }}</h3>
      <p>
        {{ result.source.publisher }} · {{ result.source.scope_year }} 年 ·
        {{ result.source.scope || '适用范围未提供' }}
      </p>
      <p class="muted">获取时间：{{ displayDate(result.snapshot.fetched_at) }}</p>
      <a
        v-if="safeSourceUrl(result.source.url)"
        :href="safeSourceUrl(result.source.url)!"
        target="_blank"
        rel="noopener noreferrer"
        >打开原网页 ↗</a
      >
      <details class="original-text">
        <summary>查看本次读取的原文与引用片段</summary>
        <pre>{{ result.snapshot.text || '未提供正文' }}</pre>
        <div
          v-for="(fragment, index) in result.snapshot.fragments"
          :key="index"
          class="evidence-block"
        >
          <strong>{{ fragment.locator }}</strong>
          <blockquote>{{ fragment.quote || '未提供引文' }}</blockquote>
        </div>
      </details>
    </section>
  </details>
</template>
