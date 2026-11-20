/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string
  readonly VITE_LOCAL_DEMO_MATTERS?: '0' | '1'
}
