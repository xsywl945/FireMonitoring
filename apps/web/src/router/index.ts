import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  scrollBehavior: () => ({ top: 0 }),
  routes: [
    { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue'), meta: { public: true, title: '登录' } },
    {
      path: '/',
      component: () => import('@/layouts/AppLayout.vue'),
      children: [
        { path: '', redirect: '/dashboard' },
        { path: 'dashboard', name: 'dashboard', component: () => import('@/views/DashboardView.vue'), meta: { title: '运行总览' } },
        { path: 'monitor', name: 'monitor', component: () => import('@/views/MonitorView.vue'), meta: { title: '实时监控' } },
        { path: 'devices', name: 'devices', component: () => import('@/views/DevicesView.vue'), meta: { title: '区域与设备' } },
        { path: 'incidents', name: 'incidents', component: () => import('@/views/IncidentsView.vue'), meta: { title: '预警事件' } },
        { path: 'incidents/:id', name: 'incident-detail', component: () => import('@/views/IncidentDetailView.vue'), meta: { title: '事件详情' } },
        { path: 'health', name: 'health', component: () => import('@/views/HealthView.vue'), meta: { title: '系统健康' } },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (to.meta.public) {
    if (to.name === 'login' && auth.isAuthenticated) return '/dashboard'
    return true
  }
  if (!auth.isAuthenticated) return { path: '/login', query: { redirect: to.fullPath } }
  await auth.restore()
  return true
})

router.afterEach((to) => {
  document.title = `${String(to.meta.title || '控制台')} · 燧巡`
})

export default router
