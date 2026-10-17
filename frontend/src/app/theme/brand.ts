import type { ThemeDefinition } from 'vuetify'

/*
  Brand tokens from docs/DBD.md (Colour palette). Both themes use the same colour names,
  so pages never need theme-specific code. Tailwind reads the same values through
  --v-theme-* (src/app/theme/tailwind.css).

  Primary is Horizon blue, a placeholder until the organization supplies branding (DBD D1):
  only the primary-* values change when it arrives.
  Status colours are reserved for status chips, map markers and timeline dots.
*/

const primaryScale = {
  'primary-50': '#EFF5FB',
  'primary-100': '#D9E7F5',
  'primary-200': '#B6D0EC',
  'primary-300': '#86B1DE',
  'primary-400': '#548CCB',
  'primary-500': '#2F6DB5',
  'primary-600': '#22569A',
  'primary-700': '#1C467E',
  'primary-800': '#1A3B66',
  'primary-900': '#183253',
  'primary-950': '#0F1F35',
}

// Station status keeps its light colours in both themes: markers sit on light OSM tiles (DBD)
const stationStatus = {
  'station-operational': '#15803D',
  'station-degraded': '#B45309',
  'station-offline': '#B91C1C',
  'station-decommissioned': '#64748B',
}

export const lightTheme: ThemeDefinition = {
  dark: false,
  colors: {
    ...primaryScale,
    ...stationStatus,

    'background': '#F8FAFC',
    'on-background': '#0F172A',
    // Behind the app's tiles (rail, pane, view): tiles stand out by colour alone (DBD "The app shell")
    'ground': '#F1F5F9',
    'surface': '#FFFFFF',
    'on-surface': '#0F172A',
    'primary': '#22569A',
    'on-primary': '#FFFFFF',

    'surface-0': '#FFFFFF',
    'surface-50': '#F8FAFC',
    'surface-100': '#F1F5F9',
    'surface-200': '#E2E8F0',
    'surface-300': '#CBD5E1',
    'surface-500': '#64748B',
    'surface-600': '#475569',
    'surface-700': '#334155',
    'surface-900': '#0F172A',

    // Feedback: the base colour is the border / icon; *-container is the banner background
    'success': '#15803D',
    'on-success': '#FFFFFF',
    'success-container': '#DCFCE7',
    'on-success-container': '#166534',
    'info': '#2F6DB5',
    'on-info': '#FFFFFF',
    'info-container': '#EFF5FB',
    'on-info-container': '#22569A',
    'warning': '#B45309',
    'on-warning': '#FFFFFF',
    'warning-container': '#FEF3C7',
    'on-warning-container': '#92400E',
    'error': '#B91C1C',
    'on-error': '#FFFFFF',
    'error-container': '#FEE2E2',
    'on-error-container': '#991B1B',

    // Request status (PRD §5.1): background, with on-* text
    'status-submitted': '#FFFFFF',
    'on-status-submitted': '#1E293B',
    'status-approved': '#E0F2FE',
    'on-status-approved': '#075985',
    'status-assigned': '#DBEAFE',
    'on-status-assigned': '#1E40AF',
    'status-scheduled': '#E0E7FF',
    'on-status-scheduled': '#3730A3',
    'status-in-progress': '#EDE9FE',
    'on-status-in-progress': '#5B21B6',
    'status-client-review': '#FEF3C7',
    'on-status-client-review': '#92400E',
    'status-reopened': '#FFEDD5',
    'on-status-reopened': '#9A3412',
    'status-closed': '#DCFCE7',
    'on-status-closed': '#166534',
    'status-denied': '#FEE2E2',
    'on-status-denied': '#991B1B',
    'status-cancelled': '#E2E8F0',
    'on-status-cancelled': '#334155',
  },
}

export const darkTheme: ThemeDefinition = {
  dark: true,
  colors: {
    ...primaryScale,
    ...stationStatus,
    'primary-50': '#16294A',
    'primary-900': '#0A1628',

    'background': '#0B1220',
    'on-background': '#F1F5F9',
    'ground': '#070C17',
    'surface': '#111A2E',
    'on-surface': '#F1F5F9',
    'primary': '#86B1DE',
    'on-primary': '#0F1F35',

    'surface-0': '#111A2E',
    'surface-50': '#0B1220',
    'surface-100': '#1A2539',
    'surface-200': '#263247',
    'surface-300': '#2E3A50',
    'surface-500': '#708296',
    'surface-600': '#94A3B8',
    'surface-700': '#CBD5E1',
    'surface-900': '#F1F5F9',

    'success': '#22C55E',
    'on-success': '#0B2E1A',
    'success-container': '#0B2E1A',
    'on-success-container': '#86EFAC',
    'info': '#548CCB',
    'on-info': '#0F1F35',
    'info-container': '#12233D',
    'on-info-container': '#B6D0EC',
    'warning': '#F59E0B',
    'on-warning': '#33210A',
    'warning-container': '#33210A',
    'on-warning-container': '#FCD34D',
    'error': '#DC2626',
    'on-error': '#FFFFFF',
    'error-container': '#3A1212',
    'on-error-container': '#FCA5A5',

    'status-submitted': '#111A2E',
    'on-status-submitted': '#E2E8F0',
    'status-approved': '#0C2D48',
    'on-status-approved': '#BAE6FD',
    'status-assigned': '#172554',
    'on-status-assigned': '#BFDBFE',
    'status-scheduled': '#1E1B4B',
    'on-status-scheduled': '#C7D2FE',
    'status-in-progress': '#2E1065',
    'on-status-in-progress': '#DDD6FE',
    'status-client-review': '#3D2A06',
    'on-status-client-review': '#FDE68A',
    'status-reopened': '#431407',
    'on-status-reopened': '#FED7AA',
    'status-closed': '#052E16',
    'on-status-closed': '#BBF7D0',
    'status-denied': '#450A0A',
    'on-status-denied': '#FECACA',
    'status-cancelled': '#334155',
    'on-status-cancelled': '#E2E8F0',
  },
}
