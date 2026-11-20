<script setup lang="ts">
import { computed, provide, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useWorkspace } from '../../app/useWorkspace'
import { matterPath } from '../../router/paths'
import StatePanel from '../../shared/ui/StatePanel.vue'
import MatterOverview from './MatterOverview.vue'
import { currentMatterKey } from './context'
import { describeFailure } from './errors'
import { matterStatusLabels, matterYearLabel } from './types'
import { useMatterRead } from './useMatterRead'

const route = useRoute()
const { mattersApi } = useWorkspace()
const workspaceTabs = [
  { path: 'overview', label: '事项概览' },
  { path: 'sources', label: '来源与条件' },
  { path: 'tasks', label: '阶段与任务' },
  { label: '材料写作台' },
  { path: 'plan', label: '候选计划' },
  { label: '归档记录' },
]
const matterId = computed(() => String(route.params.matterId))
const {
  data: matter,
  loading,
  error,
  reload,
} = useMatterRead(matterId, mattersApi ? (id, signal) => mattersApi.read(id, signal) : undefined)
provide(currentMatterKey, { matter, reload })
watch(
  () => route.name,
  (name) => {
    if (name === 'matter-overview') void reload()
  },
)
</script>

<template>
  <section class="page workspace-page">
    <Teleport v-if="matter" defer to="#active-workspace-name">{{ matter.goal }}</Teleport>
    <Teleport v-if="matter" defer to="#workspace-shortcuts">
      <div class="sidebar-workspaces">
        <p>我的工作区</p>
        <RouterLink class="current-workspace-link" :to="matterPath(matter.id)">
          <span aria-hidden="true">●</span> {{ matter.goal }}
        </RouterLink>
      </div>
    </Teleport>
    <div class="page-header workspace-heading">
      <div>
        <h1>{{ matter?.goal ?? '事项工作区' }}</h1>
        <p v-if="matter" class="workspace-subtitle">
          {{ matter.type_name }} · {{ matterYearLabel(matter.scope_year) }} ·
          {{ matterStatusLabels[matter.status] }}
        </p>
      </div>
      <div class="workspace-heading-actions">
        <RouterLink class="secondary-link" to="/matters">返回事项工作台</RouterLink>
        <RouterLink class="button-link" to="/matters/new">＋ 新建工作区</RouterLink>
      </div>
    </div>
    <nav class="matter-tabs" aria-label="当前事项页面">
      <template v-for="tab in workspaceTabs" :key="tab.label">
        <RouterLink v-if="tab.path" :to="matterPath(matterId, tab.path)">{{
          tab.label
        }}</RouterLink>
        <span v-else class="unavailable-tab" :aria-label="`${tab.label}尚未接入`" title="尚未接入">
          {{ tab.label }}
        </span>
      </template>
    </nav>
    <MatterOverview v-if="!mattersApi && route.name === 'matter-overview'" />
    <StatePanel
      v-else-if="!mattersApi"
      kind="unavailable"
      title="当前事项尚未读取"
      description="事项服务尚未连接，暂时无法核实事项与访问范围。连接后可继续查看。"
    />
    <StatePanel v-else-if="loading && !matter" kind="loading" title="正在读取当前事项" />
    <StatePanel
      v-else-if="error"
      kind="error"
      title="无法进入当前事项"
      :description="describeFailure(error).message"
      retry
      @retry="reload"
    />
    <RouterView v-else-if="matter" :key="matterId" />
  </section>
</template>

<style scoped>
.current-workspace-link {
  background: var(--page2-lavender);
  color: var(--page2-brand);
  font-weight: 700;
  overflow-wrap: anywhere;
}

.workspace-heading {
  align-items: flex-end;
  gap: 16px;
}

.workspace-subtitle {
  color: var(--page2-muted);
  font-size: 16px;
}

.workspace-heading-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.matter-tabs {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 6px;
  border-bottom: 1px solid var(--page2-line);
  margin-bottom: 16px;
}

.matter-tabs a,
.unavailable-tab {
  padding: 12px;
  border-radius: 8px 8px 0 0;
  background: #fff;
  color: var(--page2-ink);
  text-align: center;
  font-size: 15px;
}

.unavailable-tab {
  color: var(--page2-muted);
  background: #f5f4f8;
}

.matter-tabs a:hover,
.matter-tabs .router-link-exact-active {
  background: var(--page2-lavender);
  color: var(--page2-brand);
}

.matter-tabs .router-link-exact-active {
  font-weight: 700;
}

@media (max-width: 1090px) {
  .matter-tabs {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .workspace-heading {
    align-items: flex-start;
    flex-direction: column;
  }
}

@media (max-width: 490px) {
  .matter-tabs {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
