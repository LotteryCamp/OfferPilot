import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { agentRunProxyTimeoutMs } from './src/modules/analysis/timing'

export default defineConfig(({ mode, command, isPreview }) => {
  const env = loadEnv(mode, process.cwd(), '')
  if (
    command === 'serve' &&
    !isPreview &&
    env.VITE_LOCAL_DEMO_MATTERS === '1' &&
    !env.API_PROXY_TARGET
  ) {
    throw new Error('本地事项联调需要配置 API_PROXY_TARGET，指向真实的 Alpha 测试服务。')
  }
  const target = env.API_PROXY_TARGET
  const runProxyTimeout = target
    ? agentRunProxyTimeoutMs(env.VITE_AGENT_RUN_TIMEOUT_SECONDS)
    : undefined
  return {
    plugins: [vue()],
    server: {
      proxy: target
        ? {
            '^/api/v1/matters/[^/?]+/agent-runs/?(?:\\?|$)': {
              target,
              changeOrigin: true,
              timeout: runProxyTimeout,
              proxyTimeout: runProxyTimeout,
            },
            '/api': { target, changeOrigin: true },
          }
        : undefined,
    },
  }
})
