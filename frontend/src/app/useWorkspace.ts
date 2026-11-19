import { inject } from 'vue'
import { workspaceKey } from './integrations'

export function useWorkspace() {
  const workspace = inject(workspaceKey)
  if (!workspace) throw new Error('Workspace integration is required')
  return workspace
}
