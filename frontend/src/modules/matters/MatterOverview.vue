<script setup lang="ts">
import { computed, inject } from 'vue'
import { matterPath } from '../../router/paths'
import { currentMatterKey } from './context'
import { matterYearLabel, planStatusLabels } from './types'

const context = inject(currentMatterKey)
if (!context) throw new Error('Current matter is required')
const { matter } = context
const scopeEntries = computed(() => Object.entries(matter.value?.scope_attrs ?? {}))
</script>

<template>
  <div class="matter-overview">
    <section class="overview-banner" :role="matter ? undefined : 'status'">
      <h2>{{ matter ? '先核对来源与条件' : '当前事项尚未读取' }}</h2>
      <p v-if="matter">核对官方通知的适用范围和要求，再确认候选计划。</p>
      <p v-else>事项服务尚未连接。适用范围、关键节点和工作区状态暂无法读取。</p>
    </section>

    <div class="overview-columns">
      <div class="overview-stack">
        <section class="card overview-next">
          <h2>下一步</h2>
          <h3>核对适用范围</h3>
          <dl v-if="scopeEntries.length" class="overview-range">
            <template v-for="[name, value] in scopeEntries" :key="name">
              <dt>{{ name }}</dt>
              <dd>{{ typeof value === 'string' ? value : JSON.stringify(value) }}</dd>
            </template>
          </dl>
          <p v-else-if="matter">当前事项暂无详细的适用范围，请对照官方来源核对。</p>
          <p v-else>读取事项后可核对适用范围和个人条件。</p>
          <div class="overview-actions">
            <RouterLink v-if="matter" class="button-link" :to="matterPath(matter.id, 'sources')">
              查看来源与条件
            </RouterLink>
            <RouterLink class="secondary-link" to="/matters">返回工作台</RouterLink>
          </div>
        </section>

        <section class="card overview-card">
          <h2>工作区当前状态</h2>
          <div class="overview-records">
            <div class="overview-record">
              <div class="overview-record-heading">
                <h3>候选计划</h3>
                <span
                  class="overview-status"
                  :class="{ 'pending-status': matter?.latest_plan?.status === 'pending' }"
                >
                  {{
                    matter?.latest_plan
                      ? planStatusLabels[matter.latest_plan.status]
                      : matter
                        ? '未生成'
                        : '未读取'
                  }}
                </span>
              </div>
              <p v-if="matter?.latest_plan">当前版本 v{{ matter.latest_plan.version_no }}</p>
              <p v-else-if="matter">本人确认候选计划后生成正式任务。</p>
            </div>

            <div class="overview-record">
              <div class="overview-record-heading">
                <h3>阶段与任务</h3>
                <span class="overview-status">
                  {{ matter ? `${matter.tasks.done} / ${matter.tasks.total} 项已完成` : '未读取' }}
                </span>
              </div>
              <p v-if="matter">待完成 {{ matter.tasks.open }} 项</p>
            </div>

            <div class="overview-record">
              <div class="overview-record-heading">
                <h3>来源处理与 Agent 运行</h3>
                <span class="overview-status">暂不可查</span>
              </div>
              <p v-if="matter">当前事项详情暂未提供来源处理和运行进度。</p>
            </div>
          </div>
        </section>
      </div>

      <div class="overview-stack">
        <section class="card overview-card">
          <h2>关键节点</h2>
          <div class="overview-record">
            <h3>{{ matter ? matterYearLabel(matter.scope_year) : '适用年度暂未读取' }}</h3>
            <p v-if="matter">官方截止时间请以适用通知为准。</p>
          </div>
        </section>

        <section class="card overview-card">
          <h2>工作区入口</h2>
          <div v-if="matter" class="overview-actions">
            <RouterLink class="button-link" :to="matterPath(matter.id, 'tasks')">
              查看正式任务
            </RouterLink>
            <RouterLink class="secondary-link" :to="matterPath(matter.id, 'plan')">
              进入计划审阅
            </RouterLink>
          </div>
          <p v-else>读取当前事项后，可查看候选计划和正式任务。</p>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
.matter-overview,
.overview-stack {
  display: grid;
  align-content: start;
  gap: 16px;
  min-width: 0;
}

.overview-banner,
.overview-next {
  border: 1px solid var(--page2-line);
  border-radius: 14px;
  background: #f0edf9;
}

.overview-banner {
  padding: 14px 20px;
}

.overview-banner h2 {
  margin: 0 0 4px;
  color: var(--page2-brand);
  font-size: 19px;
}

.overview-columns {
  display: grid;
  grid-template-columns: minmax(0, 3fr) minmax(0, 1.96fr);
  gap: 20px;
}

.overview-card,
.overview-next {
  display: grid;
  align-content: start;
  gap: 14px;
  padding: 22px;
}

.overview-card h2,
.overview-next h2 {
  margin: 0;
  font-size: 22px;
}

.overview-next h3 {
  margin: 0;
  color: var(--page2-brand);
  font-size: 28px;
}

.matter-overview p {
  margin: 0;
  color: var(--page2-muted);
  font-size: 15px;
}

.overview-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.overview-records {
  display: grid;
  gap: 12px;
}

.overview-record {
  padding: 14px;
  border-radius: 9px;
  background: #f8f7fa;
}

.overview-record h3 {
  margin: 0;
  font-size: 16px;
}

.overview-record p {
  margin-top: 6px;
}

.overview-record-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 6px 12px;
}

.overview-status {
  padding: 4px 9px;
  border-radius: 6px;
  background: var(--page2-lavender);
  color: var(--page2-brand);
  font-size: 13px;
  font-weight: 700;
}

.pending-status {
  background: #ffefd7;
  color: #80541b;
}

.overview-range {
  display: grid;
  grid-template-columns: minmax(0, max-content) minmax(0, 1fr);
  gap: 8px 14px;
  margin: 0;
}

.overview-range dt {
  color: var(--page2-muted);
  overflow-wrap: anywhere;
}

.overview-range dd {
  margin: 0;
  overflow-wrap: anywhere;
}

@media (max-width: 930px) {
  .overview-columns {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
