let workspaceOwner: string | null = null

export function setWorkspaceStorageOwner(owner: string | null) {
  workspaceOwner = owner
}

export function workspaceStorageKey(key: string) {
  if (!workspaceOwner) throw new Error('当前会话尚未确认，请重新登录。')
  return `offerpilot:account:${workspaceOwner}:${key}`
}

export function clearLegacyWorkspaceStorage() {
  const legacyKeys = Object.keys(sessionStorage).filter(
    (key) => key.startsWith('offerpilot:analysis:') || key.startsWith('offerpilot.plan-decision.'),
  )
  for (const key of legacyKeys) sessionStorage.removeItem(key)
}
