import type { Role } from '@/api/models'
import {
  mdiAccountCheckOutline,
  mdiAccountGroupOutline,
  mdiDomain,
  mdiFormatListChecks,
  mdiInboxOutline,
  mdiViewDashboardOutline,
} from '@mdi/js'
import { icons } from '@/app/theme/icons'

// Menus by role (AFD §5.1). Route names are in app/router/routes.ts.

export interface MenuItem {
  label: string
  to: string
  icon: string
  /** Shown only to these roles; everyone in the shell when absent. */
  roles?: readonly Role[]
}

export const clientMenu: MenuItem[] = [
  { label: 'Dashboard', to: 'dashboard', icon: mdiViewDashboardOutline },
  { label: 'Stations', to: 'stations', icon: icons.station },
  { label: 'Map', to: 'map', icon: icons.map },
  { label: 'Requests', to: 'requests', icon: icons.request },
  { label: 'Reports', to: 'reports', icon: icons.visitReport },
]

export const staffMenu: MenuItem[] = [
  { label: 'Dashboard', to: 'dashboard', icon: mdiViewDashboardOutline },
  { label: 'Queue', to: 'queue', icon: mdiInboxOutline, roles: ['technician', 'admin'] },
  { label: 'Requests', to: 'requests', icon: icons.request },
  { label: 'Stations', to: 'stations', icon: icons.station },
  { label: 'Map', to: 'map', icon: icons.map },
  { label: 'Sensors', to: 'sensors', icon: icons.sensor },
  { label: 'Calibration', to: 'calibration', icon: icons.calibration },
  { label: 'Reports', to: 'reports', icon: icons.visitReport },
]

export const adminMenu: MenuItem[] = [
  { label: 'Registrations', to: 'admin-registrations', icon: mdiAccountCheckOutline },
  { label: 'Users', to: 'admin-users', icon: mdiAccountGroupOutline },
  { label: 'Organizations', to: 'admin-organizations', icon: mdiDomain },
  { label: 'Checklist templates', to: 'admin-checklists', icon: mdiFormatListChecks },
  { label: 'QR labels and import', to: 'admin-stations-tools', icon: icons.scanQr },
  { label: 'Audit log', to: 'admin-audit', icon: icons.history },
]

export const fieldMenu: MenuItem[] = [
  { label: 'Visit', to: 'dashboard', icon: icons.visit },
  { label: 'Scan', to: 'scan', icon: icons.scanQr },
  { label: 'Stations', to: 'stations', icon: icons.station },
  { label: 'Sync', to: 'sync', icon: icons.sync },
]

export function visibleTo (items: MenuItem[], roles: readonly Role[]): MenuItem[] {
  return items.filter(item => !item.roles || item.roles.some(r => roles.includes(r)))
}
