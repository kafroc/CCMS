import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'Login',
      component: () => import('@/views/Login.vue'),
      meta: { requiresAuth: false },
    },
    {
      path: '/',
      component: () => import('@/components/common/Layout.vue'),
      meta: { requiresAuth: true },
      children: [
        {
          path: '',
          redirect: '/risk',
        },
        {
          path: 'toes',
          name: 'TOE',
          component: () => import('@/views/toe/ToeList.vue'),
        },
        {
          path: 'toes/create',
          name: 'TOECreate',
          component: () => import('@/views/toe/ToeCreate.vue'),
        },
        {
          path: 'toes/:id',
          name: 'TOEDetail',
          component: () => import('@/views/toe/ToeDetail.vue'),
        },
        {
          path: 'threats',
          name: 'Threats',
          component: () => import('@/views/threat/ThreatManage.vue'),
        },
        {
          path: 'security',
          name: 'Security',
          component: () => import('@/views/security/SecurityList.vue'),
        },
        {
          path: 'tests',
          name: 'Tests',
          component: () => import('@/views/test/TestList.vue'),
        },
        {
          path: 'risk',
          name: 'Risk',
          component: () => import('@/views/dashboard/RiskDashboard.vue'),
        },
        {
          path: 'export',
          name: 'Export',
          component: () => import('@/views/export/ExportST.vue'),
        },
        {
          path: 'users',
          name: 'Users',
          component: () => import('@/views/user/UserList.vue'),
          meta: { requiresAdmin: true },
        },
        {
          path: 'ai-models',
          name: 'AIModels',
          component: () => import('@/views/aimodel/AIModelList.vue'),
        },
        {
          path: 'settings',
          name: 'Settings',
          component: () => import('@/views/settings/Settings.vue'),
        },
      ],
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/',
    },
  ],
})

// Route guards
router.beforeEach((to, _from, next) => {
  const authStore = useAuthStore()

  if (to.meta.requiresAuth !== false && !authStore.isLoggedIn) {
    next('/login')
    return
  }

  if (to.meta.requiresAdmin && !authStore.isAdmin) {
    next('/')
    return
  }

  if (to.path === '/login' && authStore.isLoggedIn) {
    next('/')
    return
  }

  next()
})

export default router
