import axios from 'axios'
import { z } from 'zod'
import { http } from '../../shared/http'
import { authenticatedAccountSchema, type LoginInput, type RegisterInput } from './contracts'

export async function registerAccount(input: RegisterInput) {
  const response = await http.post<unknown>('/auth/register', input)
  return authenticatedAccountSchema.parse(response.data)
}

export async function loginAccount(input: LoginInput) {
  const response = await http.post<unknown>('/auth/login', input)
  return authenticatedAccountSchema.parse(response.data)
}

export async function readAccount() {
  const response = await http.get<unknown>('/auth/me')
  return authenticatedAccountSchema.parse(response.data)
}

export async function logoutAccount() {
  const response = await http.post('/auth/logout')
  if (response.status !== 204) throw new Error('退出响应未得到确认')
}

const errorBody = z.object({
  error: z.object({
    code: z.string(),
    message: z.string(),
    details: z
      .object({ issues: z.array(z.object({ path: z.string(), message: z.string() })).optional() })
      .optional(),
  }),
})

export interface AuthProblem {
  message: string
  code: string
  status?: number
  fields?: Record<string, string>
  retryAfter?: string
}

export function authFailure(cause: unknown): AuthProblem {
  if (axios.isAxiosError(cause)) {
    const status = cause.response?.status
    const body = errorBody.safeParse(cause.response?.data)
    if (body.success && status !== undefined && status < 500) {
      const error = body.data.error
      const fields = Object.fromEntries(
        (error.details?.issues ?? []).map((issue) => [
          issue.path.replace(/^body\./, ''),
          issue.message,
        ]),
      )
      const retryAfter = cause.response?.headers['retry-after']
      const messages: Record<string, string> = {
        authentication_required: '登录已失效，请重新登录后继续。',
        invalid_credentials: '邮箱或密码不正确，或账号当前不可用。请核对后重试。',
        invalid_current_password: '当前密码不正确。',
        email_already_registered: '此邮箱已注册。请返回登录或更换邮箱。',
        validation_error: '请检查填写的信息。',
        too_many_login_attempts: '登录尝试过于频繁，请稍后重试。',
      }
      return {
        code: error.code,
        message: messages[error.code] ?? error.message,
        status,
        fields,
        retryAfter: retryAfter === undefined ? undefined : String(retryAfter),
      }
    }
    return {
      code: 'service_unavailable',
      status,
      message: '暂时无法确认账号操作结果，请检查网络和服务连接，重新核对登录状态。',
    }
  }
  return {
    code: 'unverified_response',
    message: '账号服务返回的结果无法核验，请重新确认登录状态。',
  }
}
