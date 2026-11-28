import { defineStore } from 'pinia'
import { ref } from 'vue'
import { cancelWorkspaceRequests, setWorkspaceSessionRevision } from '../../shared/http'
import {
  changeSession,
  isCurrentSessionRevision,
  onSessionRevisionChanged,
  readSessionRevision,
  waitForStableSession,
} from '../../shared/sessionCoordination'
import {
  clearLegacyWorkspaceStorage,
  setWorkspaceStorageOwner,
} from '../../shared/workspaceStorage'
import { useSourcesStore } from '../sources/store'
import {
  authFailure,
  loginAccount,
  logoutAccount,
  readAccount,
  registerAccount,
  type AuthProblem,
} from './api'
import type { Account, AuthenticatedAccount, LoginInput, RegisterInput, Session } from './contracts'

type AuthStatus = 'idle' | 'checking' | 'authenticated' | 'anonymous' | 'unavailable'
type AuthOperation = 'login' | 'register' | 'logout'

export const useAuthStore = defineStore('auth', () => {
  const status = ref<AuthStatus>('idle')
  const user = ref<Account | null>(null)
  const session = ref<Session | null>(null)
  const problem = ref<AuthProblem | null>(null)
  const pending = ref<AuthOperation | null>(null)
  const workspaceVersion = ref(0)
  const sources = useSourcesStore()
  let checking: Promise<void> | null = null
  let generation = 0
  let observedRevision: string | null = null

  function clearWorkspace() {
    cancelWorkspaceRequests()
    setWorkspaceSessionRevision(null)
    sources.cancel()
    sources.$patch({ sources: [], currentMatterId: '', error: '', loadedAt: null, loading: false })
    setWorkspaceStorageOwner(null)
    workspaceVersion.value++
    user.value = null
    session.value = null
  }

  function accept(result: AuthenticatedAccount, revision: string) {
    if (user.value?.id !== result.user.id || user.value.workspace_id !== result.user.workspace_id) {
      clearWorkspace()
    }
    setWorkspaceStorageOwner(result.user.id)
    setWorkspaceSessionRevision(revision)
    observedRevision = revision
    try {
      clearLegacyWorkspaceStorage()
    } catch {
      // Storage availability is handled by the individual workspace operations.
    }
    user.value = result.user
    session.value = result.session
    problem.value = null
    status.value = 'authenticated'
  }

  function expireSession() {
    if (status.value !== 'authenticated' && status.value !== 'checking') return false
    generation++
    clearWorkspace()
    problem.value = { code: 'authentication_required', message: '登录已失效，请重新登录后继续。' }
    status.value = 'anonymous'
    return true
  }

  function restoreSession(): Promise<void> {
    if (checking) return checking
    if (pending.value || problem.value?.code === 'logout_unconfirmed') return Promise.resolve()
    const wasAuthenticated = status.value === 'authenticated'
    const ticket = ++generation
    clearWorkspace()
    status.value = 'checking'
    problem.value = null
    checking = (async () => {
      try {
        // A session response describes the cookie only for the revision that was read.
        while (ticket === generation) {
          const revision = await waitForStableSession()
          if (ticket !== generation) return
          let result: AuthenticatedAccount
          try {
            result = await readAccount()
          } catch (cause) {
            if (ticket !== generation) return
            if (!isCurrentSessionRevision(revision, readSessionRevision())) continue
            observedRevision = revision
            throw cause
          }
          if (ticket !== generation) return
          if (!isCurrentSessionRevision(revision, readSessionRevision())) continue
          accept(result, revision)
          return
        }
      } catch (cause) {
        if (ticket !== generation) return
        const failure = authFailure(cause)
        if (failure.status === 401 && failure.code === 'authentication_required') {
          if (wasAuthenticated) problem.value = failure
          status.value = 'anonymous'
        } else {
          problem.value = failure
          status.value = 'unavailable'
        }
      } finally {
        checking = null
      }
    })()
    return checking
  }

  function ensureSession() {
    if (pending.value) return Promise.resolve()
    if (status.value === 'idle' || status.value === 'checking') return restoreSession()
    if (status.value === 'authenticated') {
      try {
        if (!isCurrentSessionRevision(observedRevision, readSessionRevision()))
          return restoreSession()
      } catch {
        return restoreSession()
      }
    }
    if (
      status.value === 'authenticated' &&
      session.value &&
      Date.parse(session.value.expires_at) <= Date.now()
    ) {
      return restoreSession()
    }
    return Promise.resolve()
  }

  function synchronizeSession() {
    if (pending.value || checking) return
    try {
      if (isCurrentSessionRevision(observedRevision, readSessionRevision())) return
    } catch {
      // Restore will surface the browser storage error without mounting private data.
    }
    if (problem.value?.code === 'logout_unconfirmed') problem.value = null
    void restoreSession()
  }

  function watchSessionChanges() {
    return onSessionRevisionChanged(synchronizeSession)
  }

  async function authenticate(
    operation: 'login' | 'register',
    request: () => Promise<AuthenticatedAccount>,
  ) {
    if (pending.value || checking || problem.value?.code === 'logout_unconfirmed') return false
    pending.value = operation
    problem.value = null
    const ticket = ++generation
    const previousStatus = status.value
    clearWorkspace()
    let recheck = false
    try {
      const { result, revision } = await changeSession(request)
      if (ticket !== generation) return false
      if (isCurrentSessionRevision(revision, readSessionRevision())) {
        accept(result, revision)
        return true
      }
      recheck = true
    } catch (cause) {
      if (ticket === generation) {
        problem.value = authFailure(cause)
        status.value = previousStatus === 'unavailable' ? 'unavailable' : 'anonymous'
        try {
          const current = readSessionRevision()
          if (!current.changing) observedRevision = current.revision
        } catch {
          observedRevision = null
        }
      }
      return false
    } finally {
      pending.value = null
    }
    if (recheck) await restoreSession()
    return status.value === 'authenticated'
  }

  function login(input: LoginInput) {
    return authenticate('login', () => loginAccount(input))
  }

  function register(input: RegisterInput) {
    return authenticate('register', () => registerAccount(input))
  }

  async function logout() {
    if (pending.value) return false
    pending.value = 'logout'
    generation++
    clearWorkspace()
    status.value = 'checking'
    problem.value = null
    let recheck = false
    try {
      const { revision } = await changeSession(logoutAccount)
      if (isCurrentSessionRevision(revision, readSessionRevision())) {
        observedRevision = revision
        status.value = 'anonymous'
        return true
      }
      recheck = true
    } catch {
      problem.value = {
        code: 'logout_unconfirmed',
        message: '服务端尚未确认退出。工作区已隐藏，请重新尝试退出。',
      }
      status.value = 'unavailable'
      return false
    } finally {
      pending.value = null
    }
    if (recheck) await restoreSession()
    return (status.value as AuthStatus) === 'anonymous'
  }

  return {
    status,
    user,
    session,
    problem,
    pending,
    workspaceVersion,
    ensureSession,
    restoreSession,
    login,
    register,
    logout,
    expireSession,
    synchronizeSession,
    watchSessionChanges,
  }
})
