import { createRouter, createWebHistory } from "vue-router"
import { currentRole, signedIn } from "../api/client"
import AppLayout from "../layouts/AppLayout.vue"
import AlertDetailView from "../views/AlertDetailView.vue"
import AlertsView from "../views/AlertsView.vue"
import CamerasView from "../views/CamerasView.vue"
import ConfigView from "../views/ConfigView.vue"
import LoginView from "../views/LoginView.vue"
import MonitorView from "../views/MonitorView.vue"
import RoomDetailView from "../views/RoomDetailView.vue"
import RoomsView from "../views/RoomsView.vue"

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/login", component: LoginView },
    {
      path: "/",
      component: AppLayout,
      children: [
        { path: "", redirect: "/rooms" },
        { path: "rooms", component: RoomsView, meta: { title: "教室管理" } },
        { path: "rooms/:id", component: RoomDetailView, meta: { title: "教室详情", parent: "教室管理" } },
        { path: "cameras", component: CamerasView, meta: { title: "摄像头管理" } },
        { path: "monitor", component: MonitorView, meta: { title: "实时监控" } },
        { path: "alerts", component: AlertsView, meta: { title: "告警研判" } },
        { path: "alerts/:id", component: AlertDetailView, meta: { title: "告警详情", parent: "告警研判" } },
        { path: "config", component: ConfigView, meta: { title: "系统配置", admin: true } },
      ],
    },
  ],
})

router.beforeEach((to) => {
  if (to.path !== "/login" && !signedIn()) return "/login"
  if (to.path === "/login" && signedIn()) return "/rooms"
  if (to.meta.admin && currentRole() !== "admin") return "/rooms"
})
