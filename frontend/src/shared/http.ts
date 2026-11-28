import axios, { CanceledError, type InternalAxiosRequestConfig } from 'axios'
import {
  isCurrentSessionRevision,
  readSessionRevision,
  withWorkspaceRequest,
} from './sessionCoordination'

export const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 15000,
  withCredentials: true,
})

let workspaceController = new AbortController()
let onAuthenticationRequired: (() => void) | undefined
let onSessionChanged: (() => void) | undefined
let workspaceRevision: string | null = null
const requestScopes = new WeakMap<InternalAxiosRequestConfig, AbortSignal>()
const sessionPaths = new Set(['/auth/register', '/auth/login', '/auth/me', '/auth/logout'])

export function cancelWorkspaceRequests() {
  workspaceController.abort()
  workspaceController = new AbortController()
}

export function setAuthenticationRequiredHandler(handler: () => void) {
  onAuthenticationRequired = handler
}

export function setSessionChangedHandler(handler: () => void) {
  onSessionChanged = handler
}

export function setWorkspaceSessionRevision(revision: string | null) {
  workspaceRevision = revision
}

function requireCurrentSession(scope: AbortSignal) {
  if (scope.aborted) throw new CanceledError()
  let current = false
  try {
    current = isCurrentSessionRevision(workspaceRevision, readSessionRevision())
  } catch {
    // A session that cannot be synchronized must be confirmed again before business access.
  }
  if (!current) {
    onSessionChanged?.()
    throw new CanceledError('账户会话已变化，请重新确认登录状态。')
  }
}

http.interceptors.request.use((config) => {
  const path = config.url?.split('?')[0]
  if (path && sessionPaths.has(path) && (path !== '/auth/me' || config.method === 'get')) {
    return config
  }
  const scope = workspaceController.signal
  requireCurrentSession(scope)
  requestScopes.set(config, scope)
  config.signal = config.signal ? AbortSignal.any([scope, config.signal as AbortSignal]) : scope
  return config
})

const transport = axios.getAdapter(http.defaults.adapter)
http.defaults.adapter = async (config) => {
  const scope = requestScopes.get(config)
  if (!scope) return transport(config)
  const signal = config.signal as AbortSignal
  try {
    return await withWorkspaceRequest(() => {
      requireCurrentSession(scope)
      return transport(config)
    }, signal)
  } catch (cause) {
    if (signal.aborted) throw new CanceledError()
    throw cause
  }
}

http.interceptors.response.use(
  (response) => {
    const scope = requestScopes.get(response.config)
    if (scope) requireCurrentSession(scope)
    return response
  },
  (cause: unknown) => {
    if (axios.isAxiosError(cause) && cause.config) {
      const scope = requestScopes.get(cause.config)
      if (scope) requireCurrentSession(scope)
      if (
        scope &&
        cause.response?.status === 401 &&
        cause.response.data?.error?.code === 'authentication_required'
      ) {
        onAuthenticationRequired?.()
      }
    }
    throw cause
  },
)
