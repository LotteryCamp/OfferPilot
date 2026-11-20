<script setup lang="ts">
import { ref } from 'vue'
import { useWorkspace } from '../../app/useWorkspace'
import { matterPath } from '../../router/paths'
import StatePanel from '../../shared/ui/StatePanel.vue'
import { describeFailure } from './errors'
import { matterStatusLabels, matterYearLabel, type Matter } from './types'
import { useMatterRead } from './useMatterRead'

const { mattersApi } = useWorkspace()
const { data, loading, error, reload } = useMatterRead(
  ref('matters'),
  mattersApi ? (_, signal) => mattersApi.list(signal) : undefined,
)

const workflow = ['建立独立工作区', '核对来源与条件', '确认计划与推进', '审阅材料并归档']

function scopeLocation(scope: Matter['scope_attrs']) {
  return [scope?.school, scope?.college]
    .filter((value): value is string => typeof value === 'string' && Boolean(value.trim()))
    .join(' · ')
}
</script>

<template>
  <section class="page workbench">
    <Teleport to="#workspace-shortcuts" defer>
      <div v-if="data?.length" class="sidebar-workspaces">
        <p>我的工作区</p>
        <RouterLink v-for="matter in data" :key="matter.id" :to="matterPath(matter.id)">
          <span aria-hidden="true">●</span> {{ matter.goal }}
        </RouterLink>
      </div>
    </Teleport>
    <div class="page-header workbench-heading">
      <div>
        <h1>每一步，都在掌握之中。</h1>
        <p class="muted">从一项具体的机会开始，把要求、任务和材料放在一起。</p>
      </div>
      <RouterLink class="button-link" to="/matters/new">＋ 新建工作区</RouterLink>
    </div>
    <div class="inline-note">
      <span aria-hidden="true">▣</span> 当前可新建推免事项。确认候选计划后，任务才会进入你的工作区。
    </div>
    <StatePanel
      v-if="!mattersApi"
      kind="unavailable"
      title="暂时无法读取你的事项"
      description="事项服务尚未连接。你可以先填写新建表单，待服务连接后再保存。"
    />
    <StatePanel
      v-else-if="loading"
      kind="loading"
      title="正在读取事项"
      description="请稍候，正在获取你的工作区。"
    />
    <StatePanel
      v-else-if="error"
      kind="error"
      title="事项读取失败"
      :description="describeFailure(error).message"
      retry
      @retry="reload"
    />
    <StatePanel
      v-else-if="data?.length === 0"
      kind="empty"
      title="还没有事项"
      description="新建一个推免事项，开始整理你的准备工作。"
      ><RouterLink class="button-link" to="/matters/new">新建第一个事项</RouterLink></StatePanel
    >
    <div v-else-if="data" class="matter-grid" aria-label="事项列表">
      <article v-for="matter in data" :key="matter.id">
        <RouterLink class="card matter-card" :to="matterPath(matter.id)">
          <span class="matter-icon" aria-hidden="true">▱</span>
          <span class="matter-type"
            >{{ matter.type_name }} · {{ matterStatusLabels[matter.status] }}</span
          >
          <h2>{{ matter.goal }}</h2>
          <p v-if="scopeLocation(matter.scope_attrs)">{{ scopeLocation(matter.scope_attrs) }}</p>
          <p>{{ matterYearLabel(matter.scope_year) }}</p>
          <div class="matter-card-footer">
            <span>任务 {{ matter.tasks.total }} 项 · 已完成 {{ matter.tasks.done }} 项</span>
            <strong>进入工作区 <span aria-hidden="true">→</span></strong>
          </div>
        </RouterLink>
      </article>
    </div>
    <section class="card workflow-panel" aria-labelledby="workflow-title">
      <h2 id="workflow-title">先核对，再行动</h2>
      <ol>
        <li v-for="(step, index) in workflow" :key="step">
          <span aria-hidden="true">0{{ index + 1 }}</span>
          <strong>{{ step }}</strong>
        </li>
      </ol>
    </section>
  </section>
</template>

<style scoped>
.workbench-heading {
  min-height: 78px;
}
.matter-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}
.matter-grid article {
  min-width: 0;
}
.matter-card {
  display: flex;
  height: 100%;
  min-height: 275px;
  flex-direction: column;
  align-items: flex-start;
  gap: 9px;
  padding: 20px;
  color: var(--page2-ink);
}
.matter-card:hover {
  border-color: #c8bcdf;
  text-decoration: none;
}
.matter-card h2 {
  margin: 0;
  font-size: 21px;
  overflow-wrap: anywhere;
}
.matter-card p {
  margin: 0;
  color: var(--page2-muted);
  overflow-wrap: anywhere;
}
.matter-icon {
  display: inline-grid;
  place-items: center;
  width: 46px;
  height: 40px;
  border-radius: 8px;
  background: #f0ecf8;
  color: var(--page2-brand);
  font-size: 21px;
}
.matter-type {
  padding: 3px 9px;
  border-radius: 8px;
  background: #f3eff8;
  color: #594970;
  font-size: 13px;
}
.matter-card-footer {
  display: flex;
  width: 100%;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  gap: 6px 12px;
  margin-top: auto;
  color: var(--page2-muted);
  font-size: 14px;
}
.matter-card-footer strong {
  color: var(--page2-brand);
  font-size: 15px;
}
.workflow-panel {
  margin-top: 16px;
  padding: 20px;
}
.workflow-panel ol {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  list-style: none;
  margin: 14px 0 0;
  padding: 0;
}
.workflow-panel li {
  min-width: 0;
  border-radius: 9px;
  padding: 10px 12px;
  background: #f5f2f9;
  color: #48395f;
}
.workflow-panel li span {
  display: block;
  color: var(--page2-muted);
  font-size: 13px;
}
@media (max-width: 1150px) {
  .matter-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 960px) {
  .workflow-panel ol {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 580px) {
  .matter-grid {
    grid-template-columns: 1fr;
  }
}
</style>
