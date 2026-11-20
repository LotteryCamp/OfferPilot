import type { InjectionKey } from 'vue'
import { connectLocalDemoMatters } from '../modules/matters/localDemoApi'
import type { Matter, MattersApi } from '../modules/matters/types'

type WorkspaceModule = (new () => {
  $props: { matterId: string; matter: Readonly<Matter> }
  $emit: (event: 'changed') => void
}) & {
  // Vue's default $emit accepts any event. Check its declared emits as well.
  emits?: { changed: () => unknown } | string[]
}

export interface WorkspaceIntegrations {
  mattersApi?: MattersApi
  identity?: { mode: 'single-user-local'; label: string }
  modules?: {
    sources?: WorkspaceModule
    plan?: WorkspaceModule
    tasks?: WorkspaceModule
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
