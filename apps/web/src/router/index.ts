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
        { path: '', redirect: '/monitor' },
        { path: 'rooms', name: 'rooms', component: () => import('@/views/RoomsView.vue'), meta: { title: '教室与摄像头' } },
        { path: 'analysis', name: 'analysis', component: () => import('@/views/AnalysisView.vue'), meta: { title: '大模型研判' } },
        { path: 'monitor', name: 'monitor', component: () => import('@/views/MonitorView.vue'), meta: { title: '火灾识别与预警' } },
        { path: 'incidents', name: 'incidents', component: () => import('@/views/IncidentsView.vue'), meta: { title: '预警响应' } },
        { path: 'incidents/:id', name: 'incident-detail', component: () => import('@/views/IncidentDetailView.vue'), meta: { title: '响应详情' } },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/monitor' },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (to.meta.public) {
    if (to.name === 'login' && auth.isAuthenticated) return '/monitor'
    return true
  }
  if (!auth.isAuthenticated) return { path: '/login', query: { redirect: to.fullPath } }
  await auth.restore()
  return true
})

router.afterEach((to) => {
  document.title = `${String(to.meta.title || '控制台')} · 火灾监控科研原型`
})

export default router
