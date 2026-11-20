import { z } from 'zod'
import { isMatterId } from '../../router/paths'
import { createMatterSchema, matterSchema, type MattersApi } from './types'

export interface SharedHttpClient {
  request<T>(config: {
    method: 'GET' | 'POST'
    url: string
    data?: unknown
    signal?: AbortSignal
  }): Promise<{ data: T }>
}

const singleSchema = z.object({ matter: matterSchema })
const listSchema = z.object({ matters: z.array(matterSchema) })

export function createMattersApi(client: SharedHttpClient): MattersApi {
  return {
    async list(signal) {
      const { data } = await client.request<unknown>({ method: 'GET', url: '/matters', signal })
      return listSchema.parse(data).matters
    },
    async read(id, signal) {
      if (!isMatterId(id)) throw new Error('事项编号格式无效')
      const { data } = await client.request<unknown>({
        method: 'GET',
        url: `/matters/${encodeURIComponent(id)}`,
        signal,
      })
      const matter = singleSchema.parse(data).matter
      if (matter.id.toLowerCase() !== id.toLowerCase())
        throw new Error('服务返回的事项与当前页面不一致，请返回列表重新进入')
      return matter
    },
    async create(input) {
      const { data } = await client.request<unknown>({
        method: 'POST',
        url: '/matters',
        data: createMatterSchema.parse(input),
      })
      return singleSchema.parse(data).matter
    },
  }
}
