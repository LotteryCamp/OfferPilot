<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { ElAlert, ElButton, ElEmpty, ElSkeleton } from 'element-plus'
import type { Matter } from '../matters/types'
import RequirementList from './RequirementList.vue'
import SourceImport from './SourceImport.vue'
import RankingSupplement from './RankingSupplement.vue'
import { useSourcesStore } from './store'
import {
  displayDate,
  initialSnapshot,
  normalizeMatterId,
  safeSourceUrl,
  statusLabel,
} from './presentation'

const props = defineProps<{ matterId: string; matter: Matter }>()
const emit = defineEmits<{ changed: [] }>()
const store = useSourcesStore()
const { sources, loading, error, loadedAt } = storeToRefs(store)
const matterId = computed(() => normalizeMatterId(props.matterId))
const selectedSourceId = ref('')
const selectedSnapshotId = ref('')
const selectedSource = computed(() =>
  sources.value.find((item) => item.id === selectedSourceId.value),
)
const selectedSnapshot = computed(() =>
  selectedSource.value?.snapshots.find((item) => item.id === selectedSnapshotId.value),
)
const snapshots = computed(() =>
  [...(selectedSource.value?.snapshots ?? [])].sort((a, b) => b.version_no - a.version_no),
)
const sourceUrl = computed(() => safeSourceUrl(selectedSource.value?.url ?? ''))
const requirementCount = computed(() =>
  sources.value.reduce(
    (total, item) =>
      total + item.snapshots.reduce((sum, version) => sum + version.requirements.length, 0),
    0,
  ),
)
const displayedSelfCheckCount = computed(
  () => selectedSnapshot.value?.requirements.filter((rule) => rule.self_check).length ?? 0,
)

watch(
  matterId,
  (id) => {
    selectedSourceId.value = ''
    selectedSnapshotId.value = ''
    if (id) void store.load(id)
    else store.cancel()
  },
  { immediate: true },
)

watch(sources, (items) => {
  if (!items.some((item) => item.id === selectedSourceId.value))
    selectedSourceId.value = items[0]?.id ?? ''
})

watch(selectedSource, (item) => {
  if (!item?.snapshots.some((version) => version.id === selectedSnapshotId.value)) {
    selectedSnapshotId.value = item ? (initialSnapshot(item)?.id ?? '') : ''
  }
})
onUnmounted(store.cancel)

function reload() {
  if (matterId.value) void store.load(matterId.value)
}

function sourceRead() {
  reload()
  emit('changed')
}

const availableSnapshots = computed(
  () =>
    new Set(
      sources.value.flatMap((item) => item.snapshots.map((version) => `${item.id}/${version.id}`)),
    ),
)

function openEvidence(sourceId: string, snapshotId: string) {
  if (!availableSnapshots.value.has(`${sourceId}/${snapshotId}`)) return
  selectedSourceId.value = sourceId
  selectedSnapshotId.value = snapshotId
}
</script>

<template>
  <section v-if="!matterId || matterId !== matter.id" class="card invalid-matter">
    <h2>事项标识无效</h2>
    <p>请从已有事项进入，或重新输入有效的事项标识。</p>
    <RouterLink to="/matters">返回事项工作台</RouterLink>
  </section>
  <div v-else class="business-module source-page">
    <div class="page-heading">
      <div>
        <h2>来源与条件</h2>
        <p class="muted">查看通知原文、适用范围与提取出的要求。</p>
      </div>
      <div class="module-actions">
        <RouterLink :to="{ name: 'matter-plan', params: { matterId } }" class="secondary-link"
          >审阅候选计划 →</RouterLink
        >
        <ElButton :loading="loading" @click="reload">刷新资料</ElButton>
      </div>
    </div>

    <ElAlert type="info" :closable="false" class="machine-notice">
      机器提取和程序检查仅表示处理状态。请结合原文及适用范围核对。
    </ElAlert>

    <SourceImport :matter="matter" @read="sourceRead" />
    <RankingSupplement :matter-id="matterId" />

    <div v-if="error" role="alert" class="read-error panel">
      <strong>读取未完成</strong>
      <p>{{ error }}</p>
      <p v-if="loadedAt">下方保留上次读取的资料（{{ displayDate(loadedAt) }}），可能已更新。</p>
      <ElButton type="primary" :loading="loading" @click="reload">重新读取</ElButton>
    </div>
    <section
      v-if="loading && !loadedAt"
      class="panel loading-panel"
      aria-live="polite"
      aria-busy="true"
    >
      <p>正在读取关联来源…</p>
      <ElSkeleton :rows="6" animated />
    </section>

    <template v-if="loadedAt">
      <div class="summary-row">
        <span
          ><strong>{{ sources.length }}</strong> 个关联来源</span
        >
        <span
          ><strong>{{ requirementCount }}</strong> 条要求（含历史版本）</span
        >
        <span class="muted"
          >适用年度 {{ matter.scope_year ?? '未填写' }} · 最近读取 {{ displayDate(loadedAt) }}</span
        >
      </div>
      <section v-if="!sources.length" class="panel">
        <ElEmpty description="当前事项暂无关联来源">
          <p class="empty-description">
            来源与要求或候选计划建立关联后，会显示在这里。仅登记的来源可能尚未出现在本列表。
          </p>
          <ElButton :loading="loading" @click="reload">刷新来源</ElButton>
        </ElEmpty>
      </section>

      <div v-else class="source-layout" :aria-busy="loading">
        <div class="source-content">
          <section class="panel source-list" aria-label="关联来源">
            <h2>来源文件</h2>
            <p class="muted">选择来源，查看原文和要求</p>
            <button
              v-for="item in sources"
              :key="item.id"
              type="button"
              class="source-card"
              :class="{ selected: item.id === selectedSourceId }"
              :aria-pressed="item.id === selectedSourceId"
              @click="selectedSourceId = item.id"
            >
              <span class="source-publisher">{{ item.publisher }}</span>
              <strong>{{ initialSnapshot(item)?.title || '未提供标题' }}</strong>
              <span>{{ item.scope_year }} 年 · {{ item.snapshots.length }} 个版本</span>
              <span
                >{{ statusLabel('lifecycle', item.status) }} ·
                {{ statusLabel('check', item.auto_check_status) }}</span
              >
            </button>
          </section>

          <section v-if="selectedSource" class="panel source-detail">
            <div class="section-heading">
              <div>
                <p class="eyebrow">来源详情</p>
                <h2>{{ selectedSnapshot?.title || '未提供标题' }}</h2>
              </div>
              <a
                v-if="sourceUrl"
                :href="sourceUrl"
                target="_blank"
                rel="noopener noreferrer"
                class="external-link"
                >打开原网页 ↗</a
              >
              <span v-else class="error-text">来源链接不可打开</span>
            </div>
            <dl class="metadata-grid">
              <div>
                <dt>发布主体</dt>
                <dd>{{ selectedSource.publisher }}</dd>
              </div>
              <div>
                <dt>适用年度</dt>
                <dd>{{ selectedSource.scope_year }}</dd>
              </div>
              <div class="wide">
                <dt>适用范围</dt>
                <dd>{{ selectedSource.scope || '未提供，需核对' }}</dd>
              </div>
              <div>
                <dt>来源状态</dt>
                <dd>{{ statusLabel('lifecycle', selectedSource.status) }}</dd>
              </div>
              <div>
                <dt>自动检查</dt>
                <dd>{{ statusLabel('check', selectedSource.auto_check_status) }}</dd>
              </div>
              <div>
                <dt>来源性质</dt>
                <dd>{{ statusLabel('origin', selectedSource.roi_status) }}</dd>
              </div>
              <div>
                <dt>有效期</dt>
                <dd>
                  {{ selectedSource.valid_from || '未提供开始日' }} 至
                  {{ selectedSource.valid_to || '未提供结束日' }}
                </dd>
              </div>
              <div class="wide">
                <dt>原网页</dt>
                <dd class="break-text">{{ selectedSource.url }}</dd>
              </div>
            </dl>

            <div class="version-bar">
              <label for="snapshot-version">查看快照</label>
              <select id="snapshot-version" v-model="selectedSnapshotId">
                <option v-for="version in snapshots" :key="version.id" :value="version.id">
                  v{{ version.version_no }} · {{ version.is_current ? '当前版本' : '历史版本' }}
                </option>
              </select>
            </div>
            <p v-if="!selectedSnapshot" class="muted">此来源尚无可查看的快照。</p>
            <template v-else>
              <ElAlert
                v-if="!selectedSnapshot.is_current"
                type="warning"
                :closable="false"
                title="正在查看历史版本，请留意其适用时间。"
              />
              <dl class="metadata-grid snapshot-metadata">
                <div>
                  <dt>发布日期</dt>
                  <dd>{{ displayDate(selectedSnapshot.published_date) }}</dd>
                </div>
                <div>
                  <dt>获取时间</dt>
                  <dd>{{ displayDate(selectedSnapshot.fetched_at) }}</dd>
                </div>
              </dl>
              <details class="original-text">
                <summary>查看快照原文与内容指纹</summary>
                <p class="break-text muted">
                  快照标识：{{ selectedSnapshot.id }}<br />SHA-256：{{
                    selectedSnapshot.content_hash
                  }}
                </p>
                <pre>{{ selectedSnapshot.text || '此快照未提供原文正文。' }}</pre>
                <div
                  v-for="(fragment, index) in selectedSnapshot.fragments"
                  :key="index"
                  class="evidence-block"
                >
                  <strong>{{ fragment.locator }}</strong>
                  <blockquote>{{ fragment.quote || '未提供引文' }}</blockquote>
                </div>
              </details>
            </template>
          </section>
        </div>

        <div class="source-content">
          <RequirementList
            v-if="selectedSnapshot"
            :snapshot="selectedSnapshot"
            :available-snapshots="availableSnapshots"
            @open-evidence="openEvidence"
          />

          <aside class="panel personal-check">
            <p class="eyebrow">个人条件</p>
            <h2>{{ displayedSelfCheckCount ? '辅助自查说明' : '尚无个人自查结果' }}</h2>
            <p v-if="displayedSelfCheckCount">
              当前版本有
              {{ displayedSelfCheckCount }}
              条要求提供自查结果，已按条目展示。自查仅供辅助核对，正式资格以官方认定为准。
            </p>
            <p v-else>当前展示通知中的要求，请先对照原文核对适用范围。</p>
            <hr />
            <h3>核对时请留意</h3>
            <ul>
              <li>适用年度、学院与批次是否吻合</li>
              <li>出处定位和原文是否齐全</li>
              <li>历史版本和待核对的要求</li>
            </ul>
          </aside>
        </div>
      </div>
    </template>
  </div>
</template>
