import type { MaterialTheme } from './material'
import type { ThemeDefinition } from 'vuetify'
import { materialColors, parseMaterialTheme } from './material'
import builtInFile from './material-theme.json'

/*
  Brand tokens from docs/DBD.md (Colour palette). Both themes use the same colour names,
  so pages never need theme-specific code. Tailwind reads the same values through
  --v-theme-* (src/app/theme/tailwind.css).

  The brand colours come from a Material 3 theme (decision W4-12): ./material-theme.json is the
  built-in one, and an admin can replace it for everyone from /admin/settings. material.ts maps
  it onto these token names.

  Status colours are reserved for status chips, map markers and timeline dots. They are fixed
  here and never come from a theme.
*/

const parsed = parseMaterialTheme(builtInFile, 'Built-in')
if (!parsed.ok) {
  throw new Error(`src/app/theme/material-theme.json: ${parsed.error}`)
}
export const builtInMaterial: MaterialTheme = parsed.theme

// Station status keeps its light colours in both themes: markers sit on light OSM tiles (DBD)
const stationStatus = {
  'station-operational': '#15803D',
  'station-degraded': '#B45309',
  'station-offline': '#B91C1C',
  'station-decommissioned': '#64748B',
}

// Feedback (success, warning) and request status (PRD §5.1): background, with on-* text
const lightStatus = {
  'success': '#15803D',
  'on-success': '#FFFFFF',
  'success-container': '#DCFCE7',
  'on-success-container': '#166534',
  'warning': '#B45309',
  'on-warning': '#FFFFFF',
  'warning-container': '#FEF3C7',
  'on-warning-container': '#92400E',
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
}

const darkStatus = {
  'success': '#22C55E',
  'on-success': '#0B2E1A',
  'success-container': '#0B2E1A',
  'on-success-container': '#86EFAC',
  'warning': '#F59E0B',
  'on-warning': '#33210A',
  'warning-container': '#33210A',
  'on-warning-container': '#FCD34D',
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
}

// The visit board's four kinds (DBD 1.8 "Sticky-note tints", W11-19): an accent for the card's
// top edge, icon and label, and a pale tint for the open sheet's header and the Add menu's swatch.
// Never status colours, never from the Material theme, and only ever on board elements.
const lightSticky = {
  'sticky-note': '#FFF3B0',
  'on-sticky-note': '#7A5C00',
  'sticky-task': '#D3F2DA',
  'on-sticky-task': '#1B6B34',
  'sticky-recommendation': '#FFDCD8',
  'on-sticky-recommendation': '#A8251B',
  'sticky-config': '#EADFFF',
  'on-sticky-config': '#61389A',
}

const darkSticky = {
  'sticky-note': '#3B3414',
  'on-sticky-note': '#F2D35B',
  'sticky-task': '#173A23',
  'on-sticky-task': '#7FD99A',
  'sticky-recommendation': '#45201C',
  'on-sticky-recommendation': '#FF9C92',
  'sticky-config': '#2E2343',
  'on-sticky-config': '#CDB3FA',
}

/** Vuetify's light and dark themes for a Material theme: its brand colours plus the fixed statuses. */
export function buildThemes (material: MaterialTheme): { light: ThemeDefinition, dark: ThemeDefinition } {
  return {
    light: { dark: false, colors: { ...stationStatus, ...lightStatus, ...lightSticky, ...materialColors(material, false) } },
    dark: { dark: true, colors: { ...stationStatus, ...darkStatus, ...darkSticky, ...materialColors(material, true) } },
  }
}
