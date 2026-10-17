import { createRouter, createWebHistory } from 'vue-router'
import { onSessionChange } from '@/app/auth/session'
import { APP_NAME } from '@/app/brand'
import { useSessionStore } from '@/stores/session'
import { useUpdateStore } from '@/stores/update'
import { safeNext } from './next'
import { routes } from './routes'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
  scrollBehavior: (_to, _from, saved) => saved ?? { top: 0 },
})

// Login gates and redirects (AFD §5.2). The server still checks every rule.
router.beforeEach(async to => {
  const session = useSessionStore()
  await session.bootstrap()

  if (to.meta.layout === 'public') {
    if (to.meta.guestOnly && session.user) {
      return safeNext(to.query.next) ?? { name: 'dashboard' }
    }
    return true
  }
  if (!session.user) {
    const reason = session.endedReason && session.endedReason !== 'logged_out' && session.endedReason !== 'no_session'
      ? session.endedReason
      : undefined
    return { name: 'login', query: { next: to.fullPath === '/dashboard' ? undefined : to.fullPath, reason } }
  }
  if (to.meta.roles && !session.hasAnyRole(to.meta.roles)) {
    // A page the role can't use looks the same as a missing one (AFD §5.2, ADR-16).
    return { name: 'not-found', params: { pathMatch: to.path.slice(1).split('/') }, query: to.query, hash: to.hash }
  }
  return true
})

router.afterEach(to => {
  document.title = to.meta.title ? `${to.meta.title} · ${APP_NAME}` : APP_NAME
})

// A tab still on the previous release asks for a chunk that a deploy has replaced (F9): offer the
// update instead of a broken page. Reloading at the target loads the new release.
router.onError((error: unknown, to) => {
  const message = error instanceof Error ? error.message : ''
  if (/dynamically imported module|Importing a module script failed|error loading dynamically/i.test(message)) {
    useUpdateStore().chunkFailed(to.fullPath)
  }
})

// The session ended while a private page was open (refresh failed, or logged out in another
// tab): back to /login with the reason, then to the same page (AFD §5.2, TRD §6.1.1).
onSessionChange((session, reason) => {
  const current = router.currentRoute.value
  if (session || current.meta.layout === 'public' || current.matched.length === 0) {
    return
  }
  const banner = reason && reason !== 'logged_out' && reason !== 'no_session' ? reason : undefined
  void router.replace({
    name: 'login',
    query: { next: reason === 'logged_out' ? undefined : current.fullPath, reason: banner },
  })
})

export default router
