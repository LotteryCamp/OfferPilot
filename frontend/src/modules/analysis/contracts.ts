import { z } from 'zod'

export const runResponse = z.object({
  run: z
    .object({
      run_id: z.string().min(1).max(200),
      status: z.string().min(1),
      error: z
        .object({ code: z.string(), message: z.string(), missing_fields: z.array(z.string()) })
        .nullable(),
      persisted_requirement_ids: z.array(z.uuid()),
      persisted_plan_id: z.uuid().nullable(),
      written_tasks: z.array(z.unknown()),
    })
    .refine((run) => run.status !== '等待确认' || run.persisted_plan_id !== null, {
      message: '等待确认的运行缺少已保存候选计划',
      path: ['persisted_plan_id'],
    }),
})
export type AnalysisRun = z.infer<typeof runResponse>['run']
export const analysisAttemptSchema = z.object({
  matterId: z.uuid(),
  sourceId: z.uuid(),
  operationId: z.uuid(),
  runId: z.string().min(1).max(200).nullable(),
  status: z.string().nullable(),
})
export type AnalysisAttempt = z.infer<typeof analysisAttemptSchema>

export function restoreAnalysisAttempt(raw: string, matterId: string) {
  const value = analysisAttemptSchema.parse(JSON.parse(raw))
  if (value.matterId !== matterId) throw new Error('运行记录的事项不一致')
  return value
}

export function assertStartedRun(run: AnalysisRun) {
  if (run.written_tasks.length || run.status === '已完成')
    throw new Error('分析入口返回了意外的任务写入状态，请先核对候选和正式任务。')
  if (run.status === '等待确认' && !run.persisted_plan_id)
    throw new Error('服务未返回已保存的候选计划，分析结果尚无法确认。')
}

export function canStartAnotherRun(status: string | undefined | null) {
  return (
    status == null ||
    ['等待用户', '等待确认', '已完成', '失败', '已取消', '已中断'].includes(status)
  )
}

export function runStatusText(run: AnalysisRun) {
  const labels: Record<string, string> = {
    运行中: '分析仍在运行，请查询状态。',
    等待用户: '分析需要补充或核对信息，请查看原因及来源依据。',
    等待确认: '候选已生成，保存结果以来源及候选页面重新读取的内容为准。',
    已完成: '该运行已完成，请重新读取候选决定及正式任务。',
    失败: '本次分析失败，可核对原因后重新发起。',
    已取消: '该运行已取消，可重新发起分析。',
    已中断: '上次分析已中断，原运行不会继续。请核对已保存结果，也可重新发起分析。',
  }
  return Object.hasOwn(labels, run.status) ? labels[run.status]! : `待识别的运行状态：${run.status}`
}
