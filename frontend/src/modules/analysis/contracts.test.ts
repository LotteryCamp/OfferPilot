import { describe, expect, it } from 'vitest'
import {
  assertStartedRun,
  canStartAnotherRun,
  restoreAnalysisAttempt,
  runResponse,
  runStatusText,
} from './contracts'

describe('分析运行与已保存候选的边界', () => {
  const run = {
    run_id: 'run-6f1c0e37c2ab',
    status: '等待确认',
    persisted_requirement_ids: [],
    persisted_plan_id: 'e0000000-0000-4000-8000-000000000001',
    written_tasks: [],
    error: null,
  }

  it('读取实际运行标识格式，不把它当成 UUID', () => {
    expect(runResponse.parse({ run }).run.run_id).toBe(run.run_id)
    expect(() => assertStartedRun(run)).not.toThrow()
  })

  it('等待确认必须有已保存的候选标识', () => {
    expect(() => assertStartedRun({ ...run, persisted_plan_id: null })).toThrow('候选计划')
    expect(runResponse.safeParse({ run: { ...run, persisted_plan_id: null } }).success).toBe(false)
  })

  it('发起分析不能宣称正式任务已创建', () => {
    expect(() => assertStartedRun({ ...run, written_tasks: [{}] })).toThrow('任务写入')
    expect(() => assertStartedRun({ ...run, status: '已完成' })).toThrow('任务写入')
  })

  it('HTTP 成功响应里的失败状态仍显示失败和原因', () => {
    const result = runResponse.parse({
      run: {
        ...run,
        status: '失败',
        persisted_plan_id: null,
        error: { code: 'VALIDATION_FAILED', message: '要求无法保存', missing_fields: [] },
      },
    }).run
    expect(result.error?.message).toBe('要求无法保存')
    expect(runStatusText(result)).toContain('失败')
  })

  it.each(['运行中', 'future_status', 'constructor'])('状态 %s 不允许直接新建运行', (status) => {
    expect(canStartAnotherRun(status)).toBe(false)
  })

  it.each(['等待用户', '等待确认', '失败', '已取消', '已完成', null])(
    '状态 %s 可由用户重新发起',
    (status) => {
      expect(canStartAnotherRun(status)).toBe(true)
    },
  )

  it('未知状态保持中性说明', () => {
    expect(runStatusText({ ...run, status: 'future_status' })).toBe(
      '待识别的运行状态：future_status',
    )
    expect(runStatusText({ ...run, status: 'constructor' })).toContain('待识别')
  })
})

describe('刷新后的运行标识校验', () => {
  const matterId = 'a0000000-0000-4000-8000-000000000001'
  const attempt = {
    matterId,
    sourceId: 'b0000000-0000-4000-8000-000000000001',
    operationId: 'c0000000-0000-4000-8000-000000000001',
    runId: 'run-6f1c0e37c2ab',
    status: '等待确认',
  }
  it('仅恢复当前事项的运行标识', () => {
    expect(restoreAnalysisAttempt(JSON.stringify(attempt), matterId)).toEqual(attempt)
    expect(() =>
      restoreAnalysisAttempt(JSON.stringify(attempt), 'a0000000-0000-4000-8000-000000000002'),
    ).toThrow('事项不一致')
  })
  it('丢失或损坏的标识不能变成已完成', () => {
    expect(() => restoreAnalysisAttempt('{', matterId)).toThrow()
    expect(() =>
      restoreAnalysisAttempt(JSON.stringify({ ...attempt, operationId: 'bad' }), matterId),
    ).toThrow()
    const pending = { ...attempt, runId: null, status: null }
    expect(restoreAnalysisAttempt(JSON.stringify(pending), matterId).status).toBeNull()
  })
})
