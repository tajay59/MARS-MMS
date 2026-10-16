import { createRouter, createWebHistory } from 'vue-router'

// Routes follow docs/AFD.md §3. Shells, guards and the remaining pages arrive in IP Phase 1.
const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'dashboard',
      component: () => import('@/features/dashboard/DashboardPage.vue'),
    },
  ],
})

export default router
