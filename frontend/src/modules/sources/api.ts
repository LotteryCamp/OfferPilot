import axios from 'axios'
import { z } from 'zod'
import { assertMatterBoundary, sourceReadResponse, sourceResponse } from './contracts'
import { http as client } from '../../shared/http'

export async function readSources(matterId: string, signal: AbortSignal) {
  const sourcesResult = await client.get<unknown>(`/matters/${matterId}/sources`, { signal })
  const { sources } = sourceResponse.parse(sourcesResult.data)
  assertMatterBoundary(sources, matterId)
  return sources
}

export async function readPublicSource(
  matterId: string,
  input: { url: string; publisher: string; scope_year: number; scope?: string },
  signal: AbortSignal,
) {
  const response = await client.post<unknown>(`/matters/${matterId}/sources/read`, input, {
    signal,
    timeout: 45000,
  })
  const result = sourceReadResponse.parse(response.data)
  if (
    result.snapshot.source_id !== result.source.id ||
    result.source.scope_year !== input.scope_year
  )
    throw new Error('返回的来源与快照不一致，请重新核对。')
  return result
}

export function isRetryableReadStatus(status: number | undefined): boolean {
  return status === undefined || status === 408 || status === 429 || (status >= 500 && status < 600)
}

export function readFailure(error: unknown): { message: string; retainData: boolean } {
  if (error instanceof z.ZodError) {
    return {
      message: '接口返回的数据格式与来源页面约定不一致，请联系后端核对。',
      retainData: false,
    }
  }
  if (axios.isAxiosError(error)) {
    const status = error.response?.status
    const messages: Record<number, string> = {
      401: '登录状态已失效，请重新登录后读取当前事项。',
      403: '当前事项无访问权限。',
      404: '未找到事项或来源接口，请核对事项标识与后端版本。',
      422: '后端未接受当前事项标识，请核对后重试。',
    }
    const message = status !== undefined ? messages[status] : undefined
    return {
      message:
        message ??
        (error.code === 'ECONNABORTED'
          ? '读取超时，请稍后重试。'
          : '暂时无法读取来源，请检查后端是否启动后重试。'),
      retainData: isRetryableReadStatus(status),
    }
  }
  return {
    message: error instanceof Error ? error.message : '来源读取失败，请重试。',
    retainData: false,
  }
}
