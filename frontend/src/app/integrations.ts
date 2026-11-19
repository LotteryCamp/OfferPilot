import type { Component, InjectionKey } from 'vue'
import { connectLocalDemoMatters } from '../modules/matters/localDemoApi'
import type { MattersApi } from '../modules/matters/types'

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

export const workspaceIntegrations: WorkspaceIntegrations = enableLocalDemo
  ? {
      mattersApi: connectLocalDemoMatters(),
      identity: { mode: 'single-user-local', label: '单用户本地演示' },
    }
  : {}
