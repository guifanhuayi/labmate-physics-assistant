import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import type { Role } from '../api/client'
import LoginPage from '../pages/LoginPage.vue'
import StudentWorkspacePage from '../pages/StudentWorkspacePage.vue'
import StudentAssignmentPage from '../pages/StudentAssignmentPage.vue'
import ManagementPage from '../pages/ManagementPage.vue'


const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/login' },
  { path: '/login', name: 'login', component: LoginPage, meta: { public: true } },
  { path: '/change-password', redirect: '/' },
  { path: '/student', name: 'student', component: StudentWorkspacePage, meta: { role: 'student' } },
  { path: '/student/assignments/:id', name: 'student-assignment', component: StudentAssignmentPage, meta: { role: 'student' } },
  { path: '/teacher', name: 'teacher', component: ManagementPage, meta: { role: 'teacher' } },
  { path: '/admin', name: 'admin', component: ManagementPage, meta: { role: 'admin' } },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

export const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  try {
    await auth.bootstrap()
  } catch {
    if (to.name !== 'login') return { name: 'login', query: { reason: 'network' } }
    return true
  }

  if (to.meta.public) {
    if (!auth.user) return true
    return auth.homePath
  }
  if (!auth.user) return { name: 'login', query: { redirect: to.fullPath } }
  const routeRole = to.meta.role as Role | undefined
  if (routeRole && routeRole !== auth.user.role) return auth.homePath
  return true
})
