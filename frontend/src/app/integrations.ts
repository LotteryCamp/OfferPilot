import { defineAsyncComponent, type InjectionKey } from 'vue'
import { createMattersApi } from '../modules/matters/api'
import type { Matter, MattersApi } from '../modules/matters/types'
import { http } from '../shared/http'

type WorkspaceModule = (new () => {
  $props: { matterId: string; matter: Readonly<Matter> }
  $emit: (event: 'changed') => void
}) & {
  // Vue's default $emit accepts any event. Check its declared emits as well.
  emits?: { changed: () => unknown } | string[]
}

export interface WorkspaceIntegrations {
  mattersApi?: MattersApi
  modules?: {
    sources?: WorkspaceModule
    plan?: WorkspaceModule
    tasks?: WorkspaceModule
  }
}

export const workspaceKey: InjectionKey<WorkspaceIntegrations> = Symbol('workspace')

export const workspaceIntegrations: WorkspaceIntegrations = {
  mattersApi: createMattersApi(http),
  modules: {
    sources: defineAsyncComponent(() => import('../modules/sources/SourceConditionsPage.vue')),
    plan: defineAsyncComponent(() => import('../modules/plans/PlanReviewPage.vue')),
    tasks: defineAsyncComponent(() => import('../modules/tasks/MatterTasksPage.vue')),
  },
}
