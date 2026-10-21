import type { Role } from '@/api/models'
import type { RouteRecordRaw } from 'vue-router'

/*
  Routes from docs/AFD.md §3. Pages built in later phases point at PlannedPage, so the shells'
  menus work on staging from the start. The server checks every rule again; `roles` only decides
  which page to show (AFD §5.2).
*/

declare module 'vue-router' {
  interface RouteMeta {
    /** Shown in the tab, the installed app's window title and the staff top bar. */
    title?: string
    /** public: split panel, no login. app: client or staff shell by role. field: field shell on phones. */
    layout?: 'public' | 'app' | 'field'
    /** Public pages a signed-in user skips (AFD §5.2: /login, /register, / go to /dashboard). */
    guestOnly?: boolean
    /** Who may open it; anyone signed in when absent. Others get the Not found page. */
    roles?: readonly Role[]
    /** For pages not built yet: the IP phase that delivers them. */
    phase?: number
  }
}

const STAFF = ['technician', 'admin', 'viewer'] as const
const ADMIN = ['admin'] as const

const planned = () => import('@/app/pages/PlannedPage.vue')

function later (path: string, name: string, title: string, phase: number, roles?: readonly Role[]): RouteRecordRaw {
  return { path, name, component: planned, meta: { title, layout: 'app', phase, roles } }
}

export const routes: RouteRecordRaw[] = [
  { path: '/', redirect: { name: 'dashboard' } },

  // Public (split panel)
  {
    path: '/login',
    name: 'login',
    component: () => import('@/features/auth/LoginPage.vue'),
    meta: { title: 'Log in', layout: 'public', guestOnly: true },
  },
  {
    path: '/register',
    name: 'register',
    component: () => import('@/features/auth/RegisterPage.vue'),
    meta: { title: 'Create an account', layout: 'public', guestOnly: true },
  },
  {
    path: '/register/pending',
    name: 'register-pending',
    component: () => import('@/features/auth/PendingPage.vue'),
    meta: { title: 'Waiting for approval', layout: 'public' },
  },
  {
    path: '/forgot-password',
    name: 'forgot-password',
    component: () => import('@/features/auth/ForgotPasswordPage.vue'),
    meta: { title: 'Reset your password', layout: 'public' },
  },
  {
    path: '/reset-password/:token',
    name: 'reset-password',
    component: () => import('@/features/auth/SetPasswordPage.vue'),
    props: route => ({ token: route.params.token, mode: 'reset' }),
    meta: { title: 'Set a new password', layout: 'public' },
  },
  {
    path: '/invite/:token',
    name: 'invite',
    component: () => import('@/features/auth/SetPasswordPage.vue'),
    props: route => ({ token: route.params.token, mode: 'invite' }),
    meta: { title: 'Accept invitation', layout: 'public' },
  },

  // Shared
  {
    path: '/dashboard',
    name: 'dashboard',
    component: () => import('@/features/dashboard/DashboardPage.vue'),
    meta: { title: 'Dashboard', layout: 'app' },
  },
  {
    path: '/profile',
    name: 'profile',
    component: () => import('@/features/profile/ProfilePage.vue'),
    meta: { title: 'My profile', layout: 'app' },
  },
  {
    // The list, one station when :id is set (PRD STN-5; AFD: clients see their own), the new
    // station form at /stations/new and the edit form at /stations/:id/edit (STN-1, STN-2). One
    // route, so the list in the pane stays put between them; the page sends clients away from
    // the forms and the server refuses them anyway.
    path: '/stations/:id?/:mode(edit)?',
    name: 'stations',
    component: () => import('@/features/stations/StationsPage.vue'),
    meta: { title: 'Stations', layout: 'app' },
  },
  {
    // Stations on a map (PRD MAP-1 to MAP-3); clients see their own organization's
    path: '/map',
    name: 'map',
    component: () => import('@/features/map/MapPage.vue'),
    meta: { title: 'Map', layout: 'app' },
  },
  {
    // Maintenance requests (PRD REQ-1 to REQ-16): the list, a request, and its form (new or edit)
    path: '/requests/new',
    name: 'request-new',
    component: () => import('@/features/requests/RequestsPage.vue'),
    meta: { title: 'New request', layout: 'app', roles: ['client', 'admin'] },
  },
  {
    path: '/requests/:id?/:mode(edit)?',
    name: 'requests',
    component: () => import('@/features/requests/RequestsPage.vue'),
    meta: { title: 'Requests', layout: 'app' },
  },
  later('/reports', 'reports', 'Reports', 7),
  later('/notifications', 'notifications', 'Notifications', 3),

  // Staff
  {
    path: '/queue',
    name: 'queue',
    component: () => import('@/features/requests/QueuePage.vue'),
    meta: { title: 'Queue', layout: 'app', roles: ['technician', 'admin'] },
  },
  {
    // The catalogue of sensor models, with their documents and units (CAL-1, DOC-1)
    path: '/sensors/:id?',
    name: 'sensors',
    component: () => import('@/features/sensors/SensorsPage.vue'),
    meta: { title: 'Sensors', layout: 'app', roles: STAFF },
  },
  {
    path: '/calibration',
    name: 'calibration',
    component: () => import('@/features/calibration/CalibrationDuePage.vue'),
    meta: { title: 'Calibration due', layout: 'app', roles: STAFF },
  },

  // Field (staff on phones)
  {
    path: '/scan',
    name: 'scan',
    component: () => import('@/features/scan/ScanPage.vue'),
    meta: { title: 'Scan', layout: 'field', roles: STAFF },
  },
  {
    // The address on every station label (PRD QR-2). Clients open it too: their camera app scans a
    // label, and the server answers 404 for a station that is not theirs (QR-4).
    path: '/s/:token',
    name: 'scan-result',
    component: () => import('@/features/scan/ScanLandingPage.vue'),
    props: true,
    meta: { title: 'Scan', layout: 'field' },
  },
  {
    path: '/sync',
    name: 'sync',
    component: () => import('@/features/field/SyncPage.vue'),
    meta: { title: 'Sync', layout: 'field', roles: STAFF },
  },

  // Admin
  {
    path: '/admin/registrations/:id?',
    name: 'admin-registrations',
    component: () => import('@/features/admin/RegistrationsPage.vue'),
    meta: { title: 'Registrations', layout: 'app', roles: ADMIN },
  },
  {
    path: '/admin/users',
    name: 'admin-users',
    component: () => import('@/features/admin/UsersPage.vue'),
    meta: { title: 'Users', layout: 'app', roles: ADMIN },
  },
  later('/admin/organizations', 'admin-organizations', 'Organizations', 2, ADMIN),
  later('/admin/checklists', 'admin-checklists', 'Checklist templates', 4, ADMIN),
  {
    // Label sheets (PRD QR-6); the station import joins this page later
    path: '/admin/stations-tools',
    name: 'admin-stations-tools',
    component: () => import('@/features/admin/StationToolsPage.vue'),
    meta: { title: 'QR labels and import', layout: 'app', roles: ADMIN },
  },
  later('/admin/audit', 'admin-audit', 'Audit log', 7, ADMIN),
  {
    // Appearance (the admin's own) and the organization's brand colours (W4-11, W4-12)
    path: '/admin/settings/:part(appearance|colours)?',
    name: 'admin-settings',
    component: () => import('@/features/settings/SettingsPage.vue'),
    meta: { title: 'Settings', layout: 'app', roles: ADMIN },
  },

  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/app/pages/NotFoundPage.vue'),
    meta: { title: 'Page not found', layout: 'app' },
  },
]
