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
    /**
     * Opens with no signal for someone unlocked with the device PIN (OFF-10). `record` means only
     * with an :id in the address, because the list needs the server. Everything else shows
     * "This needs a connection".
     */
    offline?: true | 'record'
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

  {
    // The device PIN opens the field work when the app starts with no signal (AUTH-12). Public
    // shell, but not guestOnly: the guard sends it where it belongs.
    path: '/unlock',
    name: 'unlock',
    component: () => import('@/features/auth/UnlockPage.vue'),
    meta: { title: 'Unlock', layout: 'public' },
  },

  // Shared
  {
    // Where a page that needs the server sends someone unlocked with no signal (AFD §5.2)
    path: '/needs-connection',
    name: 'needs-connection',
    component: () => import('@/app/pages/NeedsConnectionPage.vue'),
    meta: { title: 'Needs a connection', layout: 'field', offline: true },
  },
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
    component: () => import('@/features/offline/StationsGate.vue'),
    meta: { title: 'Stations', layout: 'app', offline: 'record' },
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
    // A client reviews the finished work and signs it off, or sends it back (PRD REQ-12, REQ-13; AFD
    // J8). Online only, and clients only: the email and the reminders link here.
    path: '/requests/:id/review',
    name: 'request-review',
    component: () => import('@/features/requests/review/ReviewPage.vue'),
    meta: { title: 'Review the work', layout: 'app', roles: ['client'] },
  },
  {
    // A client's own report on a request, as a PDF or an online form (PRD CRP-1 to CRP-4; AFD J9)
    path: '/requests/:id/client-reports/new',
    name: 'client-report-new',
    component: () => import('@/features/requests/clientReports/ClientReportPage.vue'),
    meta: { title: 'Add a client report', layout: 'app', roles: ['client'] },
  },
  {
    path: '/requests/:id/client-reports/:reportId',
    name: 'client-report-draft',
    component: () => import('@/features/requests/clientReports/ClientReportPage.vue'),
    meta: { title: 'Add a client report', layout: 'app', roles: ['client'] },
  },
  {
    path: '/requests/:id?/:mode(edit)?',
    name: 'requests',
    component: () => import('@/features/requests/RequestsPage.vue'),
    meta: { title: 'Requests', layout: 'app' },
  },
  {
    // Visits (PRD VIS-1 to VIS-4, VIS-11): the list, and one visit when :id is set. A client sees
    // their organization's visits, read only.
    path: '/visits/:id?',
    name: 'visits',
    component: () => import('@/features/offline/VisitsGate.vue'),
    meta: { title: 'Visits', layout: 'app', offline: 'record' },
  },
  {
    // A started visit on a phone (AFD J6, W12): its stations, and each station's board. Phones are
    // sent here from /visits/:id once the visit has started; the page sends other screens back.
    path: '/visits/:id/field',
    name: 'visit-field',
    component: () => import('@/features/offline/VisitFieldGate.vue'),
    meta: { title: 'Visit', layout: 'field', roles: STAFF, offline: true },
  },
  {
    // A visit's report (PRD RPT-2, RPT-4 to RPT-6; AFD J7): edit, sign, finalize and reopen. Staff only;
    // needs a connection like every report action (OFF-10). A client reads a final report on the visit.
    path: '/visit-reports/:id',
    name: 'visit-report',
    component: () => import('@/features/visits/report/editor/ReportEditorPage.vue'),
    meta: { title: 'Visit report', layout: 'app', roles: STAFF },
  },
  later('/reports', 'reports', 'Reports', 7),
  {
    // The person's own notifications (PRD NOT-1, NOT-2)
    path: '/notifications',
    name: 'notifications',
    component: () => import('@/features/notifications/NotificationsPage.vue'),
    meta: { title: 'Notifications', layout: 'app' },
  },

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
    meta: { title: 'Scan', layout: 'field', roles: STAFF, offline: true },
  },
  {
    // The address on every station label (PRD QR-2). Clients open it too: their camera app scans a
    // label, and the server answers 404 for a station that is not theirs (QR-4).
    path: '/s/:token',
    name: 'scan-result',
    component: () => import('@/features/scan/ScanLandingPage.vue'),
    props: true,
    meta: { title: 'Scan', layout: 'field', offline: true },
  },
  {
    // The W13 iOS check (risk R4): test files kept on the phone and read back after a restart
    path: '/sync/storage-check',
    name: 'storage-check',
    component: () => import('@/features/field/StorageCheckPage.vue'),
    meta: { title: 'Storage check', layout: 'field', roles: STAFF, offline: true },
  },
  {
    path: '/sync',
    name: 'sync',
    component: () => import('@/features/field/SyncPage.vue'),
    meta: { title: 'Sync', layout: 'field', roles: STAFF, offline: true },
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
