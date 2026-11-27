import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { agentRunProxyTimeoutMs } from './src/modules/analysis/timing'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
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
