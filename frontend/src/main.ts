import { createApp } from 'vue'
import { ElButton, ElConfigProvider, ElForm, ElFormItem, ElInput, ElTag } from 'element-plus'
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/form/style/css'
import 'element-plus/es/components/form-item/style/css'
import 'element-plus/es/components/input/style/css'
import 'element-plus/es/components/tag/style/css'
import './app/theme.css'
import App from './App.vue'
import { router } from './router'
import { workspaceIntegrations, workspaceKey } from './app/integrations'

createApp(App)
  .provide(workspaceKey, workspaceIntegrations)
  .use(router)
  .use(ElButton)
  .use(ElConfigProvider)
  .use(ElForm)
  .use(ElFormItem)
  .use(ElInput)
  .use(ElTag)
  .mount('#app')
