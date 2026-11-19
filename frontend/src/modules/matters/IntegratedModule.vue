<script setup lang="ts">
import { computed, inject } from 'vue'
import { useWorkspace } from '../../app/useWorkspace'
import StatePanel from '../../shared/ui/StatePanel.vue'
import { currentMatterKey } from './context'

const props = defineProps<{ section: 'sources' | 'plan' | 'tasks' }>()
const workspace = useWorkspace()
const context = inject(currentMatterKey)
if (!context) throw new Error('Current matter is required')
const { matter } = context
const component = computed(() => workspace.modules?.[props.section])
const titles = {
  sources: '来源与条件页面尚未接入',
  plan: '候选计划审阅尚未接入',
  tasks: '个人任务页面尚未接入',
}
</script>

<template>
  <component
    :is="component"
    v-if="component && matter"
    :key="matter.id"
    :matter-id="matter.id"
    :matter="matter"
    @changed="context.reload"
  />
  <StatePanel
    v-else
    kind="unavailable"
    :title="titles[section]"
    description="当前事项已读取。此页面连接后会展示服务端的实际内容，你可以先返回事项概览。"
  />
</template>
