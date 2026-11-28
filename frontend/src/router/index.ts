import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../modules/auth/store'
import { safeReturnPath } from './auth-navigation'
import { isMatterId, matterPath } from './paths'

export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', redirect: '/matters' },
    {
      path: '/login',
      name: 'login',
      component: () => import('../modules/auth/AuthPage.vue'),
      props: { mode: 'login' },
      meta: { title: '登录', public: true },
    },
    {
      path: '/register',
      name: 'register',
      component: () => import('../modules/auth/AuthPage.vue'),
      props: { mode: 'register' },
      meta: { title: '注册', public: true },
    },
    {
      path: '/account',
      name: 'account',
      component: () => import('../modules/auth/AccountPage.vue'),
      meta: { title: '个人账户' },
    },
    {
      path: '/matters',
      name: 'matters',
      component: () => import('../modules/matters/MattersList.vue'),
      meta: { title: '事项工作台' },
    },
    {
      path: '/matters/new',
      name: 'matter-new',
      component: () => import('../modules/matters/MatterCreate.vue'),
      meta: { title: '新建工作区' },
    },
    {
      path: '/matters/:matterId',
      component: () => import('../modules/matters/MatterWorkspace.vue'),
      beforeEnter: (to) => (isMatterId(to.params.matterId) ? true : { name: 'not-found' }),
      children: [
        { path: '', redirect: (to) => matterPath(String(to.params.matterId)) },
        {
          path: 'overview',
          name: 'matter-overview',
          component: () => import('../modules/matters/MatterOverview.vue'),
          meta: { title: '事项概览' },
        },
        ...(['sources', 'plan', 'tasks'] as const).map((section) => ({
          path: section,
          name: `matter-${section}`,
          component: () => import('../modules/matters/IntegratedModule.vue'),
          props: { section },
          meta: {
            title: { sources: '来源与条件', plan: '候选计划', tasks: '个人任务' }[section],
          },
        })),
      ],
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: () => import('../app/NotFound.vue'),
      meta: { title: '页面未找到' },
    },
  ],
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  await auth.ensureSession()
  if (to.meta.public) {
    if (auth.status === 'authenticated') return safeReturnPath(to.query.redirect)
    return true
  }
  if (auth.status === 'anonymous') {
    return {
      name: 'login',
      query: {
        redirect: safeReturnPath(to.fullPath),
        ...(auth.problem?.code === 'authentication_required' ? { reason: 'expired' } : {}),
      },
    }
  }
  if (to.params.matterId && !isMatterId(to.params.matterId)) return { name: 'not-found' }
  return true
})

router.afterEach((to) => {
  document.title = `${String(to.meta.title ?? '个人事项')} · OfferPilot`
})
