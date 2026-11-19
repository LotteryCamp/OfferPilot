import { createRouter, createWebHistory } from 'vue-router'
import { isMatterId, matterPath } from './paths'

export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', redirect: '/matters' },
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

router.beforeEach((to) => {
  if (to.params.matterId && !isMatterId(to.params.matterId)) return { name: 'not-found' }
})

router.afterEach((to) => {
  document.title = `${String(to.meta.title ?? '个人事项')} · OfferPilot`
})
