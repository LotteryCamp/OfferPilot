<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import { useWorkspace } from './app/useWorkspace'
import workspaceMark from './assets/offerpilot-mark.png'

const workspace = useWorkspace()
const route = useRoute()
const isMatter = computed(() => typeof route.params.matterId === 'string')
</script>

<template>
  <el-config-provider :locale="zhCn">
    <div class="app-shell">
      <a class="skip-link" href="#main-content">跳到主要内容</a>
      <aside class="sidebar" aria-label="工作区侧栏">
        <RouterLink class="brand" to="/matters" aria-label="OfferPilot · 事项工作台">
          <img :src="workspaceMark" class="brand-mark" width="104" height="104" alt="" />
          <strong>OfferPilot</strong>
          <span>你的大学事项领航员</span>
        </RouterLink>
        <p class="space-label">个人空间</p>
        <nav class="primary-nav" aria-label="主导航">
          <RouterLink
            :class="{ 'nav-active': !isMatter && route.name !== 'not-found' }"
            to="/matters"
          >
            <span aria-hidden="true">▦</span> 事项工作台
          </RouterLink>
          <span class="nav-unavailable" aria-disabled="true" title="时间总览暂未接入">
            <span aria-hidden="true">▣</span> 时间总览
          </span>
          <span class="nav-unavailable" aria-disabled="true" title="个人事实库暂未接入">
            <span aria-hidden="true">◎</span> 个人事实库
          </span>
        </nav>
        <div id="workspace-shortcuts" class="workspace-shortcuts" />
        <div class="sidebar-note">
          <strong><span aria-hidden="true">✧</span> Pilot 助手</strong>
          <p>从公开来源核对要求，再由你确认下一步。</p>
        </div>
      </aside>
      <div class="app-main">
        <header class="topbar">
          <nav aria-label="当前位置" class="breadcrumb">
            <RouterLink to="/matters">{{ isMatter ? '事项工作区' : '我的工作区' }}</RouterLink>
            <span aria-hidden="true">/</span>
            <template v-if="isMatter">
              <span id="active-workspace-name" />
              <span class="breadcrumb-fallback">{{ route.meta.title }}</span>
            </template>
            <span v-else>{{ route.name === 'not-found' ? '页面未找到' : '事项工作台' }}</span>
          </nav>
          <span v-if="workspace.identity?.label || !workspace.mattersApi" class="connection-label">
            {{ workspace.identity?.label ?? '事项服务未连接' }}
          </span>
        </header>
        <div
          v-if="workspace.identity?.mode === 'single-user-local'"
          class="identity-note"
          role="status"
        >
          单用户本地演示 · 当前服务未提供完整登录与账户隔离。
        </div>
        <main id="main-content" tabindex="-1"><RouterView /></main>
        <footer class="app-footer">
          仅辅助核对，不作正式资格结论。请在官方入口自行完成对外提交。
        </footer>
      </div>
    </div>
  </el-config-provider>
</template>
