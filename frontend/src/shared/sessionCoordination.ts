const revisionKey = 'offerpilot:session-revision'
const changePrefix = 'offerpilot:session-change:'
const mutationLock = 'offerpilot:session-mutation'
const workspaceLock = 'offerpilot:workspace-request'

export class SessionSyncError extends Error {}

export interface SessionRevision {
  revision: string
  changing: boolean
}

function storageAccess<T>(operation: (storage: Storage) => T): T {
  try {
    return operation(window.localStorage)
  } catch {
    throw new SessionSyncError('无法同步账户会话，请检查浏览器的站点存储设置。')
  }
}

function pendingKeys(storage: Storage): string[] {
  return Object.keys(storage).filter((key) => key.startsWith(changePrefix))
}

export function readSessionRevision(): SessionRevision {
  return storageAccess((storage) => ({
    revision: storage.getItem(revisionKey) ?? 'initial',
    changing: pendingKeys(storage).length > 0,
  }))
}

export function isCurrentSessionRevision(expected: string | null, current: SessionRevision) {
  return expected !== null && !current.changing && expected === current.revision
}

export function onSessionRevisionChanged(handler: () => void) {
  function receive(event: StorageEvent) {
    if (event.key === null || event.key === revisionKey || event.key.startsWith(changePrefix)) {
      handler()
    }
  }
  window.addEventListener('storage', receive)
  return () => window.removeEventListener('storage', receive)
}

function withLock<T>(
  name: string,
  mode: LockMode,
  operation: () => Promise<T>,
  signal?: AbortSignal,
) {
  const locks = navigator.locks
  return locks ? locks.request(name, { mode, signal }, operation) : operation()
}

export function withWorkspaceRequest<T>(operation: () => Promise<T>, signal: AbortSignal) {
  return withLock(workspaceLock, 'shared', operation, signal)
}

export async function waitForStableSession(): Promise<string> {
  const current = readSessionRevision()
  if (!current.changing) return current.revision
  if (!navigator.locks) {
    throw new SessionSyncError('另一个标签页正在确认会话，请待操作结束后重新检查登录状态。')
  }
  return withLock(mutationLock, 'exclusive', async () => {
    // With the mutation lock held, any remaining change marks belong to closed tabs.
    return storageAccess((storage) => {
      const pending = pendingKeys(storage)
      if (pending.length) {
        storage.setItem(revisionKey, crypto.randomUUID())
        for (const key of pending) storage.removeItem(key)
      }
      return storage.getItem(revisionKey) ?? 'initial'
    })
  })
}

export async function changeSession<T>(operation: () => Promise<T>) {
  return withLock(mutationLock, 'exclusive', async () => {
    const key = `${changePrefix}${crypto.randomUUID()}`
    storageAccess((storage) => {
      // Publish before any request that can change the shared session cookie.
      storage.setItem(key, '1')
      if (navigator.locks) {
        for (const previous of pendingKeys(storage)) {
          if (previous !== key) storage.removeItem(previous)
        }
      }
    })
    const revision = crypto.randomUUID()
    let result: T
    try {
      result = await withLock(workspaceLock, 'exclusive', operation)
    } finally {
      storageAccess((storage) => {
        // Keep the changing mark until the new revision is visible to every tab.
        storage.setItem(revisionKey, revision)
        storage.removeItem(key)
      })
    }
    return { result, revision }
  })
}
