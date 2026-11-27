<script setup lang="ts">
import { computed } from 'vue'
import { useAuthStore } from './store'
import StatePanel from '../../shared/ui/StatePanel.vue'

const auth = useAuthStore()
const expiration = computed(() => {
  if (!auth.session) return '—'
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(
    new Date(auth.session.expires_at),
  )
})
</script>

<template>
  <section class="page narrow account-page" aria-labelledby="account-title">
    <header class="page-header">
      <div>
        <h1 id="account-title">账户信息</h1>
        <p class="muted">查看当前账户和登录会话。</p>
      </div>
      <RouterLink class="secondary-link" to="/matters">返回事项工作台</RouterLink>
    </header>
    <div v-if="auth.status === 'authenticated' && auth.user && auth.session" class="account-cards">
      <section class="card account-profile" aria-labelledby="profile-title">
        <h2 id="profile-title">个人账户</h2>
        <div class="account-name">
          <span class="account-avatar" aria-hidden="true">{{
            Array.from(auth.user.display_name)[0]
          }}</span>
          <div>
            <strong>{{ auth.user.display_name }}</strong>
            <p>{{ auth.user.email }}</p>
          </div>
        </div>
        <dl class="account-details">
          <div>
            <dt>账户类型</dt>
            <dd>{{ auth.user.account_type === 'admin' ? '管理员' : '普通用户' }}</dd>
          </div>
          <div>
            <dt>账户状态</dt>
            <dd>
              {{ { active: '已启用', pending: '待审批', disabled: '已停用' }[auth.user.status] }}
            </dd>
          </div>
        </dl>
      </section>
      <section class="card account-session" aria-labelledby="session-title">
        <h2 id="session-title">登录会话</h2>
        <dl class="account-details">
          <div>
            <dt>会话有效期</dt>
            <dd>
              <time :datetime="auth.session.expires_at">{{ expiration }}</time>
            </dd>
          </div>
          <div>
            <dt>记住登录</dt>
            <dd>{{ auth.session.remember ? '已启用' : '未启用' }}</dd>
          </div>
        </dl>
        <el-button :disabled="Boolean(auth.pending)" @click="auth.restoreSession()"
          >重新核对会话</el-button
        >
      </section>
    </div>
    <StatePanel
      v-else-if="auth.status === 'checking' || auth.status === 'idle'"
      kind="loading"
      title="正在核对账户信息"
    />
    <StatePanel
      v-else
      kind="error"
      title="暂时无法获取账户信息"
      :description="auth.problem?.message"
      retry
      @retry="auth.restoreSession()"
    />
  </section>
</template>

<style scoped>
.account-cards {
  display: grid;
  gap: 16px;
}
.account-profile,
.account-session {
  padding: 22px;
}
.account-name {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 8px 0 18px;
}
.account-name > div {
  min-width: 0;
  overflow-wrap: anywhere;
}
.account-name strong {
  color: var(--page2-ink);
  font-size: 20px;
}
.account-name p {
  margin: 4px 0 0;
  color: var(--page2-muted);
}
.account-avatar {
  display: inline-grid;
  flex: 0 0 56px;
  height: 56px;
  place-items: center;
  border-radius: 14px;
  background: var(--page2-lavender);
  color: var(--page2-brand);
  font-size: 24px;
  font-weight: 700;
}
.account-details {
  margin: 0 0 16px;
}
.account-details div {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 4px 16px;
  padding: 12px 0;
  border-top: 1px solid var(--page2-line);
  overflow-wrap: anywhere;
}
.account-details dt {
  color: var(--page2-muted);
}
.account-details dd {
  margin: 0;
  color: var(--page2-ink);
  font-weight: 600;
}
.account-profile .account-details {
  margin-bottom: 0;
}
</style>
