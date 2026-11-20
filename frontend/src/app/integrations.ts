import { defineAsyncComponent, type Component, type InjectionKey } from 'vue'
import { createMattersApi } from '../modules/matters/api'
import type { MattersApi } from '../modules/matters/types'
import { http } from '../shared/http'

export interface WorkspaceIntegrations {
  mattersApi?: MattersApi
  identity?: { mode: 'single-user-local'; label: string }
  modules?: {
    sources?: Component
    plan?: Component
    tasks?: Component
  }
}

export const workspaceKey: InjectionKey<WorkspaceIntegrations> = Symbol('workspace')

const enableLocalDemo = import.meta.env.DEV && import.meta.env.VITE_LOCAL_DEMO_MATTERS === '1'

export const workspaceIntegrations: WorkspaceIntegrations = {
  modules: {
    sources: defineAsyncComponent(() => import('../modules/sources/SourceConditionsPage.vue')),
    plan: defineAsyncComponent(() => import('../modules/plans/PlanReviewPage.vue')),
  },
  ...(enableLocalDemo
    ? {
        mattersApi: createMattersApi(http),
        identity: { mode: 'single-user-local' as const, label: '单用户本地演示' },
      }
    : {}),
}
