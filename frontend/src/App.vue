<script setup lang="ts">
import { computed, nextTick, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import workspaceMark from './assets/offerpilot-mark.png'
import { useAuthStore } from './modules/auth/store'
import { safeReturnPath } from './router/auth-navigation'
import StatePanel from './shared/ui/StatePanel.vue'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const isMatter = computed(() => typeof route.params.matterId === 'string')

watch(
  () => auth.status,
  async (status) => {
    if (status === 'anonymous' && route.name && !route.meta.public) {
      const redirect = safeReturnPath(route.fullPath)
      const expired = auth.problem?.code === 'authentication_required'
      await nextTick()
      if (auth.status === 'anonymous' && !route.meta.public) {
        await router.replace({
          name: 'login',
          query: { redirect, ...(expired ? { reason: 'expired' } : {}) },
        })
      }
    }
  },
)

let sessionTimer: ReturnType<typeof setTimeout> | undefined
watch(
  () => auth.session?.expires_at,
  (expiresAt) => {
    clearTimeout(sessionTimer)
    if (!expiresAt) return
    const delay = Math.min(Math.max(Date.parse(expiresAt) - Date.now(), 60_000), 2_147_000_000)
    sessionTimer = setTimeout(() => {
      if (auth.status === 'authenticated') void auth.restoreSession()
    }, delay)
  },
  { immediate: true },
)
function checkRestoredPage(event: PageTransitionEvent) {
  if (event.persisted) void auth.restoreSession()
}
window.addEventListener('pageshow', checkRestoredPage)
onUnmounted(() => {
  clearTimeout(sessionTimer)
  window.removeEventListener('pageshow', checkRestoredPage)
})

async function logout() {
  if (await auth.logout()) await router.replace({ name: 'login' })
}
</script>

<template>
  <el-config-provider :locale="zhCn">
    <RouterView v-if="route.meta.public" :key="String(route.name)" />
    <div
      v-else-if="auth.status === 'authenticated' && auth.user"
      :key="auth.workspaceVersion"
      class="app-shell"
    >
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
            :class="{ 'nav-active': route.name === 'matters' || route.name === 'matter-new' }"
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
          <RouterLink to="/account" :class="{ 'nav-active': route.name === 'account' }">
            <span aria-hidden="true">◉</span> 个人账户
          </RouterLink>
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
            <span v-else>{{ route.meta.title }}</span>
          </nav>
          <div class="account-actions">
            <RouterLink class="connection-label" to="/account">{{
              auth.user.display_name
            }}</RouterLink>
            <el-button :loading="auth.pending === 'logout'" @click="logout">退出登录</el-button>
          </div>
        </header>
        <main id="main-content" tabindex="-1"><RouterView /></main>
        <footer class="app-footer">
          仅辅助核对，不作正式资格结论。请在官方入口自行完成对外提交。
        </footer>
      </div>
    </div>
    <main v-else id="main-content" class="auth-gate" tabindex="-1">
      <div class="auth-gate-brand">
        <img :src="workspaceMark" width="76" height="76" alt="" />
        <h1>OfferPilot</h1>
      </div>
      <StatePanel
        v-if="auth.status === 'checking' || auth.status === 'idle'"
        kind="loading"
        :title="auth.pending === 'logout' ? '正在退出登录' : '正在确认登录状态'"
        description="请稍候，正在连接账户服务。"
      />
      <StatePanel
        v-else-if="auth.status === 'unavailable'"
        kind="error"
        :title="
          auth.problem?.code === 'logout_unconfirmed' ? '暂未确认退出' : '暂时无法确认登录状态'
        "
        :description="auth.problem?.message"
      >
        <el-button
          v-if="auth.problem?.code === 'logout_unconfirmed'"
          type="primary"
          @click="logout"
        >
          重新尝试退出
        </el-button>
        <div v-else class="form-actions">
          <el-button type="primary" @click="auth.restoreSession">重新确认登录状态</el-button>
          <RouterLink
            class="secondary-link"
            :to="{ name: 'login', query: { redirect: safeReturnPath(route.fullPath) } }"
            >前往登录</RouterLink
          >
        </div>
      </StatePanel>
      <StatePanel
        v-else
        kind="unavailable"
        title="请先登录"
        description="登录后即可进入你的个人工作区。"
      >
        <RouterLink
          class="button-link"
          :to="{ name: 'login', query: { redirect: safeReturnPath(route.fullPath) } }"
          >前往登录</RouterLink
        >
      </StatePanel>
    </main>
  </el-config-provider>
</template>

<style scoped>
.account-actions {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 10px;
}
.account-actions .connection-label {
  max-width: 220px;
  min-width: 0;
  overflow: hidden;
  display: block;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.auth-gate {
  width: min(100% - 32px, 520px);
  margin: 8vh auto;
}
.auth-gate-brand {
  display: flex;
  align-items: center;
  gap: 16px;
  color: var(--page2-brand);
}
.auth-gate-brand img {
  object-fit: contain;
}
@media (max-width: 700px) {
  .topbar {
    flex-wrap: wrap;
  }
  .account-actions {
    margin-left: auto;
    flex-wrap: wrap;
  }
  .account-actions .connection-label {
    max-width: 165px;
  }
}
</style>
