import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { describe, expect, it } from 'vitest'
import { useAnalysis } from './useAnalysis'

describe('分析标识的存储边界', () => {
  it('存储不可用时禁用恢复并阻止重新分析', async () => {
    expect(typeof globalThis.sessionStorage).toBe('undefined')
    let analysis: ReturnType<typeof useAnalysis> | undefined
    let reads = 0
    const app = createSSRApp({
      setup() {
        const current = useAnalysis(
          () => 'a0000000-0000-4000-8000-000000000001',
          () => {
            reads++
          },
        )
        analysis = current
        return () => h('p', current.error.value)
      },
    })
    const html = await renderToString(app)
    expect(html).toContain('浏览器中的运行标识无法核验')
    if (!analysis) throw new Error('分析组件未初始化')
    expect(analysis.storageReady.value).toBe(false)
    expect(analysis.recoverable.value).toBe(false)
    expect(
      await analysis.start('b0000000-0000-4000-8000-000000000001', {
        source_urls: ['https://math.fzu.edu.cn/info/1171/10393.htm'],
        publisher: '福州大学数学与统计学院',
        scope_year: 2027,
      }),
    ).toBeNull()
    expect(analysis.error.value).toContain('会话存储不可用')
    expect(analysis.attempt.value).toBeNull()
    expect(analysis.run.value).toBeNull()
    expect(reads).toBe(0)
  })
})
