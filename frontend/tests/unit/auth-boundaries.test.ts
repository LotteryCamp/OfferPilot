import { afterEach, describe, expect, it } from 'vitest'
import { safeReturnPath } from '../../src/router/auth-navigation'
import { setWorkspaceStorageOwner, workspaceStorageKey } from '../../src/shared/workspaceStorage'

describe('登录后的返回位置', () => {
  const id = '00000000-0000-7000-8000-000000000001'

  it.each(['/matters', '/matters/new', '/account', `/matters/${id}/sources?tab=conditions`])(
    '保留有效的工作区位置 %s',
    (path) => {
      expect(safeReturnPath(path)).toBe(path)
    },
  )

  it.each([undefined, '', '/register', '/login', '/matters/invalid', '/unknown'])(
    '缺少有效工作区目标时返回事项列表 %j',
    (path) => {
      expect(safeReturnPath(path)).toBe('/matters')
    },
  )
})

describe('账户范围内的工作区状态', () => {
  afterEach(() => setWorkspaceStorageOwner(null))

  it('不同账户读取各自命名空间，重登恢复原有标识', () => {
    const key = 'analysis:00000000-0000-7000-8000-000000000001'
    setWorkspaceStorageOwner('00000000-0000-4000-8000-000000000002')
    const first = workspaceStorageKey(key)
    setWorkspaceStorageOwner('00000000-0000-4000-8000-000000000003')
    expect(workspaceStorageKey(key)).not.toBe(first)
    setWorkspaceStorageOwner('00000000-0000-4000-8000-000000000002')
    expect(workspaceStorageKey(key)).toBe(first)
  })

  it('未确认身份时不能读取或生成账户状态标识', () => {
    setWorkspaceStorageOwner(null)
    expect(() => workspaceStorageKey('analysis:current-matter')).toThrow('当前会话尚未确认')
  })
})
