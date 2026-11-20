import { z } from 'zod'

const errorSchema = z.object({
  kind: z.enum(['http', 'network', 'timeout', 'cancelled']).optional(),
  status: z.number().optional(),
  response: z.object({ status: z.number(), data: z.unknown() }).optional(),
})
const bodySchema = z.object({ error: z.object({ code: z.string() }) })

export function describeFailure(error: unknown, write = false) {
  if (error instanceof z.ZodError) {
    return {
      message: write
        ? '收到的创建结果无法核验。请先查看事项列表，避免重复创建。'
        : '事项数据格式与接口契约不一致，请联系项目维护者。',
      uncertain: write,
    }
  }
  const parsed = errorSchema.safeParse(error)
  const status = parsed.success ? (parsed.data.status ?? parsed.data.response?.status) : undefined
  const body = parsed.success ? bodySchema.safeParse(parsed.data.response?.data) : undefined
  const uncertain = write && (status === undefined || status === 408 || status >= 500)
  if (uncertain)
    return {
      message: '创建结果暂时无法确认。请先重新读取事项列表，核对是否已创建，再决定后续操作。',
      uncertain,
    }
  if (status === 409 && body?.success && body.data.error.code === 'template_version_missing') {
    return { message: '此事项类型尚无已发布模板。请联系管理员补齐后重试。', uncertain: false }
  }
  const message =
    status === 401
      ? '当前身份不可用，请重新连接有效会话。'
      : status === 403
        ? '当前身份没有访问此事项的权限。'
        : status === 404
          ? '未找到该事项，或当前身份无权访问。'
          : status === 409
            ? '事项状态已变化，请重新读取后再操作。'
            : status === 422
              ? '提交信息未通过校验，请检查表单内容。'
              : write
                ? '暂时无法创建工作区，请检查提交信息和服务连接后重试。'
                : '暂时无法读取事项，请检查服务连接后重试。'
  return { message, uncertain: false }
}
