<script setup lang="ts">
import { computed } from 'vue'
import { ElButton, ElTag } from 'element-plus'
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
</script>

<template>
  <StatePanel v-if="!matterId" kind="unavailable" title="当前事项尚未核实" />
  <div v-else class="business-module tasks-page" data-testid="tasks-page">
    <header class="page-heading">
      <h2>正式任务</h2>
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
    <div v-else class="task-list" data-testid="task-list" :aria-busy="loading">
      <article
        v-for="task in tasks"
        :id="`task-${task.id}`"
        :key="task.id"
        class="panel task-card"
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
              >{{ source.publisher }} · {{ source.locator }} · 快照 v{{ source.version_no }}</strong
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
    </div>
  </div>
</template>

<style scoped>
.task-list {
  display: grid;
  gap: 12px;
}

.task-card {
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
