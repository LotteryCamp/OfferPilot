import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

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
  return {
    plugins: [vue()],
    server: {
      proxy: env.API_PROXY_TARGET
        ? { '/api': { target: env.API_PROXY_TARGET, changeOrigin: true } }
        : undefined,
    },
  }
})
