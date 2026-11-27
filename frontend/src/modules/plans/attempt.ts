import { z } from 'zod'
import type { Action } from './contracts'
import { workspaceStorageKey } from '../../shared/workspaceStorage'

const attemptSchema = z.object({
  matterId: z.uuid(),
  planId: z.uuid(),
  action: z.enum(['confirm', 'reject']),
  key: z.uuid(),
})
export type Attempt = z.infer<typeof attemptSchema>

export function chooseAttempt(
  previous: Attempt | null,
  matterId: string,
  planId: string,
  action: Action,
): Attempt {
  if (previous) {
    if (
      previous.matterId !== matterId ||
      previous.planId !== planId ||
      previous.action !== action
    ) {
      throw new Error('上次决定的结果尚未确定，请先重新读取状态或重试原操作。')
    }
    return previous
  }
  return { matterId, planId, action, key: crypto.randomUUID() }
}

function storageKey(matterId: string, planId: string) {
  return workspaceStorageKey(`plan-decision:${matterId}:${planId}`)
}
export function readAttempt(matterId: string, planId: string): Attempt | null {
  const value = sessionStorage.getItem(storageKey(matterId, planId))
  if (value === null) return null
  const attempt = attemptSchema.parse(JSON.parse(value))
  if (attempt.matterId !== matterId || attempt.planId !== planId)
    throw new Error('操作标识不匹配，请联系维护者核对。')
  return attempt
}
export function saveAttempt(attempt: Attempt) {
  try {
    sessionStorage.setItem(storageKey(attempt.matterId, attempt.planId), JSON.stringify(attempt))
  } catch {
    throw new Error('无法保存本次操作标识，尚未提交决定。请检查浏览器会话存储后重新读取。')
  }
}
export function clearAttempt(matterId: string, planId: string) {
  sessionStorage.removeItem(storageKey(matterId, planId))
}
