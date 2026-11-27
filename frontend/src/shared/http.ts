import axios, { CanceledError, type InternalAxiosRequestConfig } from 'axios'

export const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 15000,
  withCredentials: true,
})

let workspaceController = new AbortController()
let onAuthenticationRequired: (() => void) | undefined
const requestScopes = new WeakMap<InternalAxiosRequestConfig, AbortSignal>()
const sessionPaths = new Set(['/auth/register', '/auth/login', '/auth/me', '/auth/logout'])

export function cancelWorkspaceRequests() {
  workspaceController.abort()
  workspaceController = new AbortController()
}

export function setAuthenticationRequiredHandler(handler: () => void) {
  onAuthenticationRequired = handler
}

http.interceptors.request.use((config) => {
  const path = config.url?.split('?')[0]
  if (path && sessionPaths.has(path) && (path !== '/auth/me' || config.method === 'get')) {
    return config
  }
  const scope = workspaceController.signal
  requestScopes.set(config, scope)
  config.signal = config.signal ? AbortSignal.any([scope, config.signal as AbortSignal]) : scope
  return config
})

http.interceptors.response.use(
  (response) => {
    if (requestScopes.get(response.config)?.aborted) throw new CanceledError()
    return response
  },
  (cause: unknown) => {
    if (axios.isAxiosError(cause) && cause.config) {
      const scope = requestScopes.get(cause.config)
      if (scope?.aborted) throw new CanceledError()
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
