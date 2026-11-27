import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { ElButton, ElConfigProvider, ElForm, ElFormItem, ElInput, ElTag } from 'element-plus'
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/form/style/css'
import 'element-plus/es/components/form-item/style/css'
import 'element-plus/es/components/input/style/css'
import 'element-plus/es/components/tag/style/css'
import 'element-plus/es/components/alert/style/css'
import 'element-plus/es/components/checkbox/style/css'
import 'element-plus/es/components/empty/style/css'
import 'element-plus/es/components/skeleton/style/css'
import './app/theme.css'
import './modules/business.css'
import App from './App.vue'
import { router } from './router'
import { workspaceIntegrations, workspaceKey } from './app/integrations'
import { useAuthStore } from './modules/auth/store'
import { setAuthenticationRequiredHandler } from './shared/http'

const pinia = createPinia()
const auth = useAuthStore(pinia)
setAuthenticationRequiredHandler(() => auth.expireSession())

createApp(App)
  .provide(workspaceKey, workspaceIntegrations)
  .use(pinia)
  .use(router)
  .use(ElButton)
  .use(ElConfigProvider)
  .use(ElForm)
  .use(ElFormItem)
  .use(ElInput)
  .use(ElTag)
  .mount('#app')
