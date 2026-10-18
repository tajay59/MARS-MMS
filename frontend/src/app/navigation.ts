import type { Role } from '@/api/models'
import {
  mdiAccountCheckOutline,
  mdiAccountGroupOutline,
  mdiClipboardTextOutline,
  mdiDomain,
  mdiFormatListChecks,
  mdiInboxOutline,
  mdiShieldAccountOutline,
  mdiViewDashboardOutline,
} from '@mdi/js'
import { icons } from '@/app/theme/icons'

/*
  Menus by role (AFD §5.1). Route names are in app/router/routes.ts.

  The app shell groups pages into sections: one icon per section on the rail (a tab on phones),
  and the section's pages as tabs at the top of the pane next to it (DBD "The app shell").
*/

export interface MenuItem {
  label: string
  to: string
  icon: string
  /** Shown only to these roles; everyone in the shell when absent. */
  roles?: readonly Role[]
}

export interface Section {
  key: string
  label: string
  /** The rail tooltip's second line: what the section holds. */
  hint: string
  icon: string
  items: MenuItem[]
  /** Routes that belong to the section without being one of its tabs. */
  also?: readonly string[]
  roles?: readonly Role[]
}

const dashboard: MenuItem = { label: 'Dashboard', to: 'dashboard', icon: mdiViewDashboardOutline }

export const adminMenu: MenuItem[] = [
  { label: 'Registrations', to: 'admin-registrations', icon: mdiAccountCheckOutline },
  { label: 'Users', to: 'admin-users', icon: mdiAccountGroupOutline },
  { label: 'Organizations', to: 'admin-organizations', icon: mdiDomain },
  { label: 'Checklist templates', to: 'admin-checklists', icon: mdiFormatListChecks },
  { label: 'QR labels and import', to: 'admin-stations-tools', icon: icons.scanQr },
  { label: 'Audit log', to: 'admin-audit', icon: icons.history },
  { label: 'Settings', to: 'admin-settings', icon: icons.configuration },
]

export const staffSections: Section[] = [
  { key: 'dashboard', label: 'Dashboard', hint: 'Status of stations and work', icon: mdiViewDashboardOutline, items: [dashboard] },
  {
    key: 'work',
    label: 'Work',
    hint: 'Queue and requests',
    icon: mdiClipboardTextOutline,
    items: [
      { label: 'Queue', to: 'queue', icon: mdiInboxOutline, roles: ['technician', 'admin'] },
      { label: 'Requests', to: 'requests', icon: icons.request },
    ],
    also: ['request-new'],
  },
  {
    key: 'stations',
    label: 'Stations',
    hint: 'Stations, map, sensors and calibration',
    icon: icons.station,
    items: [
      { label: 'Stations', to: 'stations', icon: icons.station },
      { label: 'Map', to: 'map', icon: icons.map },
      { label: 'Sensors', to: 'sensors', icon: icons.sensor },
      { label: 'Calibration', to: 'calibration', icon: icons.calibration },
    ],
  },
  {
    key: 'reports',
    label: 'Reports',
    hint: 'Visit and summary reports',
    icon: icons.visitReport,
    items: [{ label: 'Reports', to: 'reports', icon: icons.visitReport }],
  },
  {
    key: 'admin',
    label: 'Admin',
    hint: 'Registrations, users and settings',
    icon: mdiShieldAccountOutline,
    items: adminMenu,
    roles: ['admin'],
  },
]

export const clientSections: Section[] = [
  { key: 'dashboard', label: 'Dashboard', hint: 'Your stations and requests at a glance', icon: mdiViewDashboardOutline, items: [dashboard] },
  {
    key: 'stations',
    label: 'Stations',
    hint: 'Your stations and the map',
    icon: icons.station,
    items: [
      { label: 'Stations', to: 'stations', icon: icons.station },
      { label: 'Map', to: 'map', icon: icons.map },
    ],
  },
  {
    key: 'requests',
    label: 'Requests',
    hint: 'Report problems and follow progress',
    icon: icons.request,
    items: [{ label: 'Requests', to: 'requests', icon: icons.request }],
    also: ['request-new'],
  },
  {
    key: 'reports',
    label: 'Reports',
    hint: 'Visit reports to read and sign off',
    icon: icons.visitReport,
    items: [{ label: 'Reports', to: 'reports', icon: icons.visitReport }],
  },
]

export const fieldMenu: MenuItem[] = [
  { label: 'Visit', to: 'dashboard', icon: icons.visit },
  { label: 'Scan', to: 'scan', icon: icons.scanQr },
  { label: 'Stations', to: 'stations', icon: icons.station },
  { label: 'Sync', to: 'sync', icon: icons.sync },
]

function allowed (roles: readonly Role[] | undefined, mine: readonly Role[]): boolean {
  return !roles || roles.some(r => mine.includes(r))
}

export function visibleTo (items: MenuItem[], roles: readonly Role[]): MenuItem[] {
  return items.filter(item => allowed(item.roles, roles))
}

/** The sections a user sees, each with only the tabs their roles may open. */
export function sectionsFor (sections: Section[], roles: readonly Role[]): Section[] {
  return sections
    .filter(section => allowed(section.roles, roles))
    .map(section => ({ ...section, items: visibleTo(section.items, roles) }))
    .filter(section => section.items.length > 0)
}

/** The section a route belongs to; pages outside every section (profile, sync) get none. */
export function sectionOf (sections: Section[], routeName: unknown): Section | undefined {
  if (typeof routeName !== 'string') {
    return undefined
  }
  return sections.find(s => s.items.some(i => i.to === routeName) || s.also?.includes(routeName))
}
