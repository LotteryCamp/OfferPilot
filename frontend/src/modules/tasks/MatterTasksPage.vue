<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { ElButton, ElEmpty, ElTag } from 'element-plus'
import StatePanel from '../../shared/ui/StatePanel.vue'
import type { Matter } from '../matters/types'
import { useMatterRead } from '../matters/useMatterRead'
import { getTasks, planError } from '../plans/api'
import { displayDate, normalizeMatterId, safeSourceUrl, statusLabel } from '../sources/presentation'

const props = defineProps<{ matterId: string; matter: Readonly<Matter> }>()
defineEmits<{ changed: [] }>()

const matterId = computed(() => {
  const id = normalizeMatterId(props.matterId)
  return id === props.matter.id ? id : ''
})
const {
  data: tasks,
  loading,
  error,
  reload,
} = useMatterRead(matterId, (id, signal) => {
  if (!id) throw new Error('任务与当前事项不一致，已停止展示。')
  return getTasks(id, signal)
})
const tasksById = computed(() => new Map(tasks.value?.map((task) => [task.id, task])))
const filter = ref<'all' | 'done' | 'unfinished'>('all')
const filters = [
  { value: 'all', label: '全部' },
  { value: 'done', label: '已完成' },
  { value: 'unfinished', label: '未完成' },
] as const
const visibleTasks = computed(() =>
  (tasks.value ?? []).filter((task) =>
    filter.value === 'all'
      ? true
      : filter.value === 'done'
        ? task.status === 'done'
        : task.status !== 'done',
  ),
)
const statusCounts = computed(() => {
  const counts = new Map<string, number>()
  for (const task of tasks.value ?? []) counts.set(task.status, (counts.get(task.status) ?? 0) + 1)
  return [...counts].map(([status, count]) => ({ status, count }))
})

async function focusDependency(id: string) {
  filter.value = 'all'
  await nextTick()
  const target = document.getElementById(`task-${id}`)
  target?.focus()
  target?.scrollIntoView({ block: 'start', behavior: 'smooth' })
}
</script>

<template>
  <StatePanel v-if="!matterId" kind="unavailable" title="当前事项尚未核实" />
  <div v-else class="business-module tasks-page" data-testid="tasks-page">
    <header class="page-heading">
      <div>
        <h2>阶段与任务</h2>
        <p class="muted">查看已确认计划生成的正式任务、期限与前置关系。</p>
      </div>
      <div class="module-actions">
        <RouterLink class="secondary-link" :to="{ name: 'matter-plan', params: { matterId } }">
          查看候选计划
        </RouterLink>
        <ElButton data-testid="tasks-refresh" :loading="loading" @click="reload">
          重新读取
        </ElButton>
      </div>
    </header>

    <StatePanel
      v-if="error"
      kind="error"
      title="无法读取正式任务"
      :description="planError(error)"
      retry
      @retry="reload"
    />
    <StatePanel v-else-if="loading && !tasks" kind="loading" title="正在读取正式任务" />
    <StatePanel
      v-else-if="!tasks?.length"
      kind="empty"
      title="当前事项暂无正式任务"
      description="确认采用候选计划后，生成的任务会出现在这里。"
    />
    <div v-else class="tasks-layout" :aria-busy="loading">
      <section class="panel task-list" data-testid="task-list">
        <div class="section-heading">
          <h2>任务清单 · {{ tasks.length }} 项</h2>
          <span class="muted">当前显示 {{ visibleTasks.length }} 项</span>
        </div>
        <div class="module-actions filter-bar" aria-label="任务状态筛选">
          <ElButton
            v-for="entry in filters"
            :key="entry.value"
            :type="filter === entry.value ? 'primary' : undefined"
            :aria-pressed="filter === entry.value"
            @click="filter = entry.value"
            >{{ entry.label }}</ElButton
          >
        </div>
        <ElEmpty v-if="!visibleTasks.length" description="此筛选下暂无任务" :image-size="72" />
        <article
          v-for="task in visibleTasks"
          :id="`task-${task.id}`"
          :key="task.id"
          class="task-card"
          data-testid="task-item"
          :data-task-id="task.id"
          :data-plan-id="task.plan_id"
          tabindex="-1"
        >
          <div class="section-heading">
            <h3>{{ task.title }}</h3>
            <ElTag type="info">{{ statusLabel('task', task.status) }}</ElTag>
          </div>
          <dl class="metadata-grid">
            <div>
              <dt>官方截止</dt>
              <dd>{{ displayDate(task.official_deadline_at ?? task.official_deadline_date) }}</dd>
            </div>
            <div>
              <dt>建议准备日</dt>
              <dd>{{ displayDate(task.suggested_date) }}</dd>
            </div>
            <div>
              <dt>计划来源</dt>
              <dd>
                <RouterLink
                  :to="{ name: 'matter-plan', params: { matterId }, query: { plan: task.plan_id } }"
                  class="secondary-link"
                >
                  查看已确认计划
                </RouterLink>
              </dd>
            </div>
            <div class="wide">
              <dt>前置任务</dt>
              <dd v-if="!task.depends_on.length">无前置任务</dd>
              <dd v-else>
                <ul class="task-dependencies">
                  <li v-for="dependencyId in task.depends_on" :key="dependencyId">
                    <a
                      v-if="tasksById.has(dependencyId)"
                      :href="`#task-${dependencyId}`"
                      data-testid="task-dependency"
                      :data-task-id="dependencyId"
                      @click.prevent="focusDependency(dependencyId)"
                    >
                      {{ tasksById.get(dependencyId)?.title }}
                    </a>
                    <span v-else class="muted" data-testid="task-dependency-missing">
                      当前事项未返回该前置任务，请重新读取核对。
                    </span>
                  </li>
                </ul>
              </dd>
            </div>
          </dl>
          <details v-if="task.sources.length">
            <summary>查看来源依据</summary>
            <div
              v-for="source in task.sources"
              :key="`${source.snapshot_id}/${source.locator}`"
              class="evidence-block"
            >
              <strong
                >{{ source.publisher }} · {{ source.locator }} · 快照 v{{
                  source.version_no
                }}</strong
              >
              <blockquote v-if="source.quote">{{ source.quote }}</blockquote>
              <a
                v-if="safeSourceUrl(source.url)"
                :href="safeSourceUrl(source.url)!"
                target="_blank"
                rel="noopener noreferrer"
                >打开原网页 ↗</a
              >
            </div>
          </details>
        </article>
      </section>
      <aside class="source-content task-overview">
        <section class="panel decision-panel">
          <h2>任务状态</h2>
          <p class="muted">共 {{ tasks.length }} 项正式任务，执行状态以最近读取结果为准。</p>
          <dl class="task-status-counts">
            <div v-for="entry in statusCounts" :key="entry.status">
              <dt>{{ statusLabel('task', entry.status) }}</dt>
              <dd>{{ entry.count }} 项</dd>
            </div>
          </dl>
        </section>
        <RouterLink class="secondary-link" :to="{ name: 'matter-sources', params: { matterId } }">
          查看来源与条件
        </RouterLink>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.task-list {
  display: grid;
  gap: 12px;
}

.task-card {
  padding: 14px;
  background: #faf9fc;
  border-radius: 8px;
  scroll-margin-top: 16px;
}

.task-card:target {
  outline: 2px solid var(--page2-brand);
  outline-offset: -2px;
}

.task-card h3 {
  overflow-wrap: anywhere;
}

.task-dependencies {
  margin: 0;
  padding-inline-start: 1.25rem;
}

.task-dependencies a {
  color: var(--page2-brand);
  text-decoration: underline;
}

.task-card details {
  margin-top: 12px;
}
</style>
