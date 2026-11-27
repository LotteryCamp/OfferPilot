<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import workspaceMark from '../../assets/offerpilot-mark.png'
import { safeReturnPath } from '../../router/auth-navigation'
import { useAuthStore } from './store'

const props = defineProps<{ mode: 'login' | 'register' }>()
const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const form = reactive({
  email: '',
  displayName: '',
  password: '',
  confirmation: '',
  remember: false,
})
const errors = ref<Record<string, string>>({})
const submissionProblem = ref<typeof auth.problem>(null)
const showPassword = ref(false)
const submitting = ref(false)
const isRegister = computed(() => props.mode === 'register')
const busy = computed(() => submitting.value || Boolean(auth.pending) || auth.status === 'checking')
const logoutUnconfirmed = computed(() => auth.problem?.code === 'logout_unconfirmed')
const outcomeUnconfirmed = computed(() =>
  ['service_unavailable', 'unverified_response'].includes(submissionProblem.value?.code ?? ''),
)
const formDisabled = computed(
  () => busy.value || logoutUnconfirmed.value || outcomeUnconfirmed.value,
)
const destination = computed(() => safeReturnPath(route.query.redirect))
const switchRoute = computed(() => ({
  path: isRegister.value ? '/login' : '/register',
  query: destination.value === '/matters' ? {} : { redirect: destination.value },
}))
const retrySeconds = computed(() => {
  const value = submissionProblem.value?.retryAfter
  return value && /^\d+$/.test(value) ? Number(value) : null
})

let operation = 0

function clearPasswords() {
  form.password = ''
  form.confirmation = ''
  showPassword.value = false
}

onBeforeUnmount(() => {
  operation += 1
  clearPasswords()
})

watch(
  () => props.mode,
  () => {
    operation += 1
    submitting.value = false
    form.email = ''
    form.displayName = ''
    form.remember = false
    clearPasswords()
    errors.value = {}
    submissionProblem.value = null
  },
)

function clearField(field: string) {
  delete errors.value[field]
  if (field === 'password') delete errors.value.confirmation
  submissionProblem.value = null
}

function validate() {
  const problems: Record<string, string> = {}
  const email = form.email.trim()
  if (!email || !/^[^\s@]+@[^\s@]+$/.test(email) || Array.from(email).length > 160) {
    problems.email = '请输入有效的邮箱地址（最多 160 个字符）'
  }
  if (
    isRegister.value &&
    (!form.displayName.trim() || Array.from(form.displayName.trim()).length > 60)
  ) {
    problems.display_name = '请输入 1–60 个字符的显示名称'
  }
  const passwordLength = Array.from(form.password).length
  if (isRegister.value && (passwordLength < 8 || passwordLength > 128)) {
    problems.password = '密码须为 8–128 个字符'
  } else if (!passwordLength || passwordLength > 128) {
    problems.password = '请输入密码（最多 128 个字符）'
  }
  if (isRegister.value && form.confirmation !== form.password) {
    problems.confirmation = '两次输入的密码不一致'
  }
  errors.value = problems
  return Object.keys(problems).length === 0
}

async function focusFeedback() {
  await nextTick()
  const first = Object.keys(errors.value)[0]
  document.getElementById(first ? `auth-${first}` : 'auth-feedback')?.focus()
}

async function submit() {
  if (formDisabled.value) return
  submissionProblem.value = null
  if (!validate()) {
    await focusFeedback()
    return
  }

  const currentOperation = ++operation
  submitting.value = true
  try {
    const email = form.email.trim()
    const success = isRegister.value
      ? await auth.register({
          email,
          display_name: form.displayName.trim(),
          password: form.password,
        })
      : await auth.login({ email, password: form.password, remember: form.remember })

    if (currentOperation !== operation) return
    clearPasswords()
    submitting.value = false
    if (success) {
      await router.replace(destination.value)
      return
    }
    submissionProblem.value = auth.problem
    for (const [field, message] of Object.entries(auth.problem?.fields ?? {})) {
      if (['email', 'display_name', 'password'].includes(field)) errors.value[field] = message
    }
    await focusFeedback()
  } finally {
    if (currentOperation === operation) {
      clearPasswords()
      submitting.value = false
    }
  }
}

async function retrySession() {
  submissionProblem.value = null
  if (logoutUnconfirmed.value) {
    await auth.logout()
  } else {
    await auth.restoreSession()
  }
}

watch(
  () => auth.status,
  (status) => {
    if (status === 'authenticated' && !submitting.value) void router.replace(destination.value)
  },
  { immediate: true },
)
</script>

<template>
  <div class="auth-screen">
    <aside class="auth-intro" aria-label="OfferPilot 项目介绍">
      <div class="auth-brand">
        <img :src="workspaceMark" alt="" width="58" height="58" />
        <div>
          <strong>OfferPilot</strong>
          <span>你的大学事项领航员</span>
        </div>
      </div>
      <div class="intro-copy">
        <p class="intro-label">个人工作区</p>
        <h2>每一步，<br />都在掌握之中。</h2>
        <p>专注准备你的推免事项，从官方通知出发，逐步整理要求、计划与任务。</p>
        <ol class="intro-workflow">
          <li><span class="workflow-mark" aria-hidden="true" />建立独立工作区</li>
          <li><span class="workflow-mark" aria-hidden="true" />核对来源与适用条件</li>
          <li><span class="workflow-mark" aria-hidden="true" />审阅计划，确认下一步</li>
        </ol>
      </div>
      <p class="intro-footer">你可以随时返回工作区，继续已经保存的进度。</p>
    </aside>

    <main class="auth-main" aria-labelledby="auth-title">
      <div class="auth-content">
        <header class="auth-heading">
          <h1 id="auth-title">{{ isRegister ? '注册' : '登录' }}</h1>
          <p>
            {{
              isRegister
                ? '创建自己的账户，开始准备第一项事务。'
                : '欢迎回来，继续推进你的个人事项。'
            }}
          </p>
        </header>

        <div
          v-if="
            route.query.reason === 'expired' || auth.problem?.code === 'authentication_required'
          "
          class="auth-notice"
          role="status"
        >
          当前会话已失效，请重新登录。
        </div>
        <div v-if="auth.status === 'checking'" class="auth-notice" role="status">
          正在检查登录状态，请稍候。
        </div>
        <div
          v-else-if="auth.status === 'unavailable'"
          class="auth-notice auth-notice-error"
          role="status"
        >
          <p>
            {{
              logoutUnconfirmed
                ? auth.problem?.message
                : '暂时无法检查会话。请检查网络连接，或重新尝试登录。'
            }}
          </p>
          <button type="button" class="text-action" :disabled="busy" @click="retrySession">
            {{ logoutUnconfirmed ? '重新尝试退出' : '重新检查会话' }}
          </button>
        </div>

        <div
          v-if="submissionProblem || Object.keys(errors).length"
          id="auth-feedback"
          data-testid="auth-feedback"
          class="auth-notice auth-notice-error"
          tabindex="-1"
          role="alert"
        >
          <strong>{{ submissionProblem?.message ?? '请检查表单中标记的信息。' }}</strong>
          <p v-if="retrySeconds">请在 {{ retrySeconds }} 秒后重试。</p>
          <button
            v-if="outcomeUnconfirmed && auth.status !== 'unavailable'"
            type="button"
            class="text-action"
            :disabled="busy"
            @click="retrySession"
          >
            重新检查会话
          </button>
        </div>

        <form class="auth-form" novalidate :aria-busy="busy" @submit.prevent="submit">
          <div class="auth-field">
            <label for="auth-email">邮箱</label>
            <input
              id="auth-email"
              v-model="form.email"
              name="email"
              type="email"
              inputmode="email"
              autocomplete="email"
              placeholder="请输入你的邮箱"
              required
              :disabled="formDisabled"
              :aria-invalid="Boolean(errors.email)"
              :aria-describedby="errors.email ? 'auth-email-error' : undefined"
              @input="clearField('email')"
            />
            <p v-if="errors.email" id="auth-email-error" class="field-error">{{ errors.email }}</p>
          </div>

          <div v-if="isRegister" class="auth-field">
            <label for="auth-display_name">显示名称</label>
            <input
              id="auth-display_name"
              v-model="form.displayName"
              name="display_name"
              autocomplete="nickname"
              placeholder="请输入你的显示名称"
              required
              :disabled="formDisabled"
              :aria-invalid="Boolean(errors.display_name)"
              :aria-describedby="errors.display_name ? 'auth-display_name-error' : undefined"
              @input="clearField('display_name')"
            />
            <p v-if="errors.display_name" id="auth-display_name-error" class="field-error">
              {{ errors.display_name }}
            </p>
          </div>

          <div class="auth-field">
            <label for="auth-password">密码</label>
            <div class="password-field">
              <input
                id="auth-password"
                v-model="form.password"
                name="password"
                :type="showPassword ? 'text' : 'password'"
                :autocomplete="isRegister ? 'new-password' : 'current-password'"
                :placeholder="isRegister ? '设置 8–128 个字符的密码' : '请输入密码'"
                required
                :disabled="formDisabled"
                :aria-invalid="Boolean(errors.password)"
                :aria-describedby="errors.password ? 'auth-password-error' : undefined"
                @input="clearField('password')"
              />
              <button
                type="button"
                class="password-toggle"
                :disabled="formDisabled"
                :aria-pressed="showPassword"
                :aria-label="showPassword ? '隐藏密码' : '显示密码'"
                @click="showPassword = !showPassword"
              >
                {{ showPassword ? '隐藏' : '显示' }}
              </button>
            </div>
            <p v-if="errors.password" id="auth-password-error" class="field-error">
              {{ errors.password }}
            </p>
          </div>

          <div v-if="isRegister" class="auth-field">
            <label for="auth-confirmation">确认密码</label>
            <input
              id="auth-confirmation"
              v-model="form.confirmation"
              name="confirmation"
              :type="showPassword ? 'text' : 'password'"
              autocomplete="new-password"
              placeholder="再次输入密码"
              required
              :disabled="formDisabled"
              :aria-invalid="Boolean(errors.confirmation)"
              :aria-describedby="errors.confirmation ? 'auth-confirmation-error' : undefined"
              @input="clearField('confirmation')"
            />
            <p v-if="errors.confirmation" id="auth-confirmation-error" class="field-error">
              {{ errors.confirmation }}
            </p>
          </div>

          <div v-else class="remember-field">
            <label
              ><input
                v-model="form.remember"
                type="checkbox"
                name="remember"
                :disabled="formDisabled"
              />
              记住登录</label
            >
            <small>仅在自己的设备上启用</small>
          </div>

          <button class="auth-submit" type="submit" :disabled="formDisabled">
            {{
              submitting ? (isRegister ? '正在注册…' : '正在登录…') : isRegister ? '注册' : '登录'
            }}
          </button>
        </form>

        <p class="auth-switch">
          {{ isRegister ? '已经拥有账户？' : '还没有账户？' }}
          <span v-if="busy" class="switch-disabled">{{
            isRegister ? '返回登录' : '注册账号'
          }}</span>
          <RouterLink v-else :to="switchRoute">{{
            isRegister ? '返回登录' : '注册账号'
          }}</RouterLink>
        </p>
      </div>
      <footer class="auth-footer">
        仅辅助核对，不作正式资格结论。请在官方入口自行完成对外提交。
      </footer>
    </main>
  </div>
</template>

<style scoped>
.auth-screen {
  display: grid;
  grid-template-columns: minmax(320px, 0.92fr) minmax(0, 1.08fr);
  min-height: 100vh;
  background: white;
}
.auth-intro {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: clamp(32px, 6vw, 92px);
  gap: 48px;
  color: var(--page2-brand);
  background: var(--page2-lavender);
  border-right: 1px solid var(--page2-line);
}
.auth-brand {
  display: flex;
  gap: 12px;
  align-items: center;
}
.auth-brand img {
  width: 58px;
  height: 58px;
  object-fit: contain;
}
.auth-brand strong,
.auth-brand span {
  display: block;
}
.auth-brand strong {
  font-size: 25px;
  line-height: 1.3;
  letter-spacing: -0.03em;
}
.auth-brand span {
  color: var(--page2-muted);
  font-size: 14px;
}
.intro-copy {
  max-width: 440px;
}
.intro-label {
  margin: 0 0 14px;
  color: #594970;
  font-weight: 600;
}
.intro-copy h2 {
  margin: 0;
  font-size: clamp(36px, 4.3vw, 64px);
  font-weight: 800;
  line-height: 1.3;
  letter-spacing: -0.035em;
}
.intro-copy > p:not(.intro-label) {
  margin: 24px 0 0;
  max-width: 340px;
  color: #51466c;
  font-size: 17px;
  line-height: 1.8;
}
.intro-workflow {
  display: grid;
  gap: 15px;
  margin: 38px 0 0;
  padding: 0;
  list-style: none;
  font-size: 15px;
  color: #51466c;
}
.intro-workflow li {
  display: flex;
  align-items: center;
  gap: 12px;
}
.workflow-mark {
  flex: 0 0 11px;
  height: 11px;
  border-radius: 50%;
  border: 2px solid #8d7cbd;
  background: white;
}
.intro-footer {
  margin: 0;
  color: var(--page2-muted);
  font-size: 14px;
}
.auth-main {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  padding: 48px clamp(24px, 6vw, 88px) 28px;
  gap: 28px;
  min-width: 0;
}
.auth-content {
  width: min(100%, 410px);
  margin: auto 0;
}
.auth-heading {
  margin-bottom: 28px;
}
.auth-heading h1 {
  font-size: 36px;
  font-weight: 750;
  line-height: 1.3;
}
.auth-heading p {
  margin: 11px 0 0;
  color: var(--page2-muted);
  line-height: 1.6;
}
.auth-form {
  display: grid;
  gap: 18px;
}
.auth-field {
  display: grid;
  gap: 6px;
  min-width: 0;
}
.auth-field label {
  font-size: 15px;
  font-weight: 700;
  color: var(--page2-ink);
}
.auth-field input {
  width: 100%;
  min-height: 48px;
  padding: 11px 14px;
  border: 1px solid #d9d4e5;
  border-radius: 8px;
  color: var(--page2-ink);
  background: var(--page2-bg);
}
.auth-field input::placeholder {
  color: #797487;
}
.auth-field input:focus {
  border-color: var(--page2-brand);
  outline: 2px solid #e2dcef;
  outline-offset: 0;
}
.auth-field input[aria-invalid='true'] {
  border-color: #b53e54;
}
.auth-field input:disabled {
  opacity: 0.8;
}
.password-field {
  position: relative;
}
.password-field input {
  padding-right: 72px;
}
.password-toggle {
  position: absolute;
  top: 5px;
  right: 6px;
  bottom: 5px;
  width: 60px;
  padding: 0;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--page2-brand);
  cursor: pointer;
  font-size: 14px;
}
.password-toggle:hover {
  background: var(--page2-lavender);
}
.field-error {
  margin: 0;
  color: #a7293d;
  font-size: 13px;
}
.remember-field {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 5px 12px;
  justify-content: space-between;
  color: var(--page2-ink);
  font-size: 14px;
}
.remember-field label {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-height: 32px;
  cursor: pointer;
}
.remember-field input {
  width: 17px;
  height: 17px;
  margin: 0;
  accent-color: var(--page2-brand);
}
.remember-field small {
  color: var(--page2-muted);
  font-size: 13px;
}
.auth-notice {
  margin-bottom: 16px;
  padding: 12px 14px;
  border: 1px solid var(--page2-line);
  border-radius: 8px;
  background: var(--page2-lavender);
  color: var(--page2-brand);
  font-size: 14px;
  overflow-wrap: anywhere;
}
.auth-notice-error {
  border-color: #edd7dc;
  background: #fbf0f2;
  color: #96344a;
}
.auth-notice p {
  margin: 0;
}
.auth-notice strong + p {
  margin-top: 4px;
}
.text-action {
  padding: 2px 0;
  border: 0;
  background: none;
  color: inherit;
  font-weight: 700;
  cursor: pointer;
  text-decoration: underline;
}
.auth-submit {
  margin-top: 2px;
  min-height: 48px;
  border: 0;
  border-radius: 8px;
  background: var(--page2-brand);
  color: white;
  font-size: 16px;
  font-weight: 700;
  cursor: pointer;
}
.auth-submit:hover:not(:disabled) {
  background: #423681;
}
button:disabled {
  cursor: not-allowed;
  opacity: 0.65;
}
.auth-switch {
  margin: 22px 0 0;
  text-align: center;
  color: var(--page2-muted);
  font-size: 14px;
}
.auth-switch a {
  font-weight: 700;
  margin-left: 4px;
  text-decoration: underline;
  text-underline-offset: 4px;
}
.switch-disabled {
  margin-left: 4px;
  opacity: 0.6;
}
.auth-footer {
  max-width: 410px;
  color: var(--page2-muted);
  text-align: center;
  font-size: 12px;
  overflow-wrap: anywhere;
}
@media (max-width: 780px) {
  .auth-screen {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: auto 1fr;
    background: var(--page2-bg);
  }
  .auth-intro {
    gap: 18px;
    padding: 24px clamp(18px, 5vw, 40px);
    border-right: 0;
    border-bottom: 1px solid var(--page2-line);
  }
  .intro-copy,
  .intro-footer {
    display: none;
  }
  .auth-brand img {
    width: 48px;
    height: 48px;
  }
  .auth-main {
    padding: 30px 16px 22px;
    justify-content: flex-start;
    gap: 18px;
  }
  .auth-content {
    width: min(100%, 460px);
    padding: 24px;
    margin: 0;
    border: 1px solid var(--page2-line);
    border-radius: 14px;
    background: white;
  }
  .auth-heading h1 {
    font-size: 30px;
  }
}
@media (max-width: 380px) {
  .auth-content {
    padding: 18px;
  }
}
</style>
