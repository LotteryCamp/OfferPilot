import { createMattersApi, type SharedHttpClient } from './api'

const timeoutMs = 15_000

export function connectLocalDemoMatters() {
  const client: SharedHttpClient = {
    async request<T>({ method, url, data, signal }: Parameters<SharedHttpClient['request']>[0]) {
      const timeout = AbortSignal.timeout(timeoutMs)
      const response = await fetch(`/api/v1${url}`, {
        method,
        headers: {
          Accept: 'application/json',
          ...(data === undefined ? {} : { 'Content-Type': 'application/json' }),
        },
        body: data === undefined ? undefined : JSON.stringify(data),
        signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
        cache: 'no-store',
      })

      if (!response.ok) {
        const body: unknown = await response.json().catch(() => undefined)
        throw Object.assign(new Error(`事项服务返回 HTTP ${response.status}`), {
          response: { status: response.status, data: body },
        })
      }

      return { data: (await response.json()) as T }
    },
  }

  return createMattersApi(client)
}
