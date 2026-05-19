import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: HomeView,
      meta: { requiresAuth: true },
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/LoginView.vue'),
    },
    {
      path: '/project/:conversationId',
      name: 'project',
      component: () => import('../views/ProjectWorkspaceView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/generate',
      name: 'generate',
      component: () => import('../views/GenerateView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/history',
      name: 'history',
      component: () => import('../views/HistoryView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/admin',
      name: 'admin',
      component: () => import('../views/AdminView.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: '/canvas',
      name: 'canvas',
      component: () => import('../views/CanvasView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/canvas/',
      redirect: '/canvas',
    },
  ],
})

function tokenPayload(token: string): { is_admin?: boolean } | null {
  try {
    const payload = token.split('.')[1]
    if (!payload) return null
    return JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/')))
  } catch {
    return null
  }
}

router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem('token')
  if (to.meta.requiresAuth && !token) {
    next('/login')
  } else if (to.meta.requiresAdmin && (!token || !tokenPayload(token)?.is_admin)) {
    next('/')
  } else {
    next()
  }
})

export default router
