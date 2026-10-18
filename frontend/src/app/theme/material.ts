import type { MaterialTheme } from '@/api/models'

/*
  Material Theme Builder exports → the DBD colour tokens (DBD "Colour palette", decision W4-12).

  The app's colours come from a Material 3 theme: the built-in one is ./material-theme.json, and
  an admin can replace it for everyone from /admin/settings (GET/PUT /api/v1/auth/branding). Only
  the light and dark schemes and the five tonal palettes are used; the role and tone lists match
  the auth service's app/domain/branding.py, which checks the same keys.

  Status colours (request, station, success, warning) never come from a theme: they keep their
  DBD values in brand.ts so a brand change can't make two statuses look alike.
*/

export type { MaterialTheme } from '@/api/models'

export const ROLES = [
  'primary', 'surfaceTint', 'onPrimary', 'primaryContainer', 'onPrimaryContainer',
  'secondary', 'onSecondary', 'secondaryContainer', 'onSecondaryContainer',
  'tertiary', 'onTertiary', 'tertiaryContainer', 'onTertiaryContainer',
  'error', 'onError', 'errorContainer', 'onErrorContainer',
  'background', 'onBackground', 'surface', 'onSurface', 'surfaceVariant', 'onSurfaceVariant',
  'outline', 'outlineVariant', 'shadow', 'scrim', 'inverseSurface', 'inverseOnSurface',
  'inversePrimary', 'primaryFixed', 'onPrimaryFixed', 'primaryFixedDim',
  'onPrimaryFixedVariant', 'secondaryFixed', 'onSecondaryFixed', 'secondaryFixedDim',
  'onSecondaryFixedVariant', 'tertiaryFixed', 'onTertiaryFixed', 'tertiaryFixedDim',
  'onTertiaryFixedVariant', 'surfaceDim', 'surfaceBright', 'surfaceContainerLowest',
  'surfaceContainerLow', 'surfaceContainer', 'surfaceContainerHigh', 'surfaceContainerHighest',
] as const
export const SCHEMES = ['light', 'dark'] as const
export const PALETTES = ['primary', 'secondary', 'tertiary', 'neutral', 'neutral-variant'] as const
export const TONES = ['0', '5', '10', '15', '20', '25', '30', '35', '40', '50', '60', '70', '80', '90', '95', '98', '99', '100'] as const
export const NAME_MAX = 120

export type Role = typeof ROLES[number]
export type SchemeName = typeof SCHEMES[number]
export type PaletteName = typeof PALETTES[number]
export type Scheme = Record<Role, string>
export type Palette = Record<typeof TONES[number], string>

const HEX = /^#[0-9a-f]{6}$/i

export type Parsed = { ok: true, theme: MaterialTheme } | { ok: false, error: string }

function isObject (value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/**
 * Reads a Material Theme Builder export (or a theme saved by this app). Keeps only what the app
 * uses; anything else in the file (contrast variants, extended colours) is left out. The error
 * names the first thing missing, in words an admin can act on.
 */
export function parseMaterialTheme (input: unknown, fallbackName?: string): Parsed {
  if (!isObject(input) || !isObject(input.schemes) || !isObject(input.palettes)) {
    return { ok: false, error: 'This isn’t a Material theme file: it has no schemes or palettes.' }
  }
  const schemes = {} as Record<SchemeName, Scheme>
  for (const name of SCHEMES) {
    const roles = input.schemes[name]
    if (!isObject(roles)) {
      return { ok: false, error: `The file has no ${name} scheme.` }
    }
    const out = {} as Scheme
    for (const role of ROLES) {
      const value = roles[role]
      if (typeof value !== 'string' || !HEX.test(value)) {
        return { ok: false, error: `The ${name} scheme needs ${role} as a colour like #0A6780.` }
      }
      out[role] = value.toUpperCase()
    }
    schemes[name] = out
  }
  const palettes = {} as Record<PaletteName, Palette>
  for (const name of PALETTES) {
    const tones = input.palettes[name]
    if (!isObject(tones)) {
      return { ok: false, error: `The file has no ${name} palette.` }
    }
    const out = {} as Palette
    for (const tone of TONES) {
      const value = tones[tone]
      if (typeof value !== 'string' || !HEX.test(value)) {
        return { ok: false, error: `The ${name} palette needs tone ${tone} as a colour like #0A6780.` }
      }
      out[tone] = value.toUpperCase()
    }
    palettes[name] = out
  }
  const seed = typeof input.seed === 'string' && HEX.test(input.seed) ? input.seed.toUpperCase() : null
  const rawName = typeof input.name === 'string' ? input.name : fallbackName
  const name = rawName?.trim().slice(0, NAME_MAX) || null
  return { ok: true, theme: { name, seed, schemes, palettes } }
}

/** The file an admin downloads: the same shape Material Theme Builder writes, so it opens there too. */
export function toExportJson (theme: MaterialTheme): string {
  return JSON.stringify({
    name: theme.name ?? undefined,
    description: 'MARS-MMS brand colours (Material 3)',
    seed: theme.seed ?? undefined,
    coreColors: { primary: theme.seed ?? theme.schemes.light!.primary },
    extendedColors: [],
    schemes: theme.schemes,
    palettes: theme.palettes,
  }, null, 2)
}

/**
 * One theme's colours as DBD tokens (TRD §13.2: Vuetify's theme colours, which Tailwind reads
 * through --v-theme-*). Tiles are the lowest surface container in light and the low one in dark,
 * with the ground one step away, so tiles stand out by colour alone (DBD "The app shell").
 */
export function materialColors (theme: MaterialTheme, dark: boolean): Record<string, string> {
  const s = theme.schemes[dark ? 'dark' : 'light'] as Scheme
  const p = theme.palettes as Record<PaletteName, Palette>
  const primary = p.primary
  const nv = p['neutral-variant']

  return {
    // Primary scale for tints and selected states (Tailwind primary-50 … 950)
    'primary-50': dark ? primary['15'] : primary['95'],
    'primary-100': primary['90'],
    'primary-200': primary['80'],
    'primary-300': primary['70'],
    'primary-400': primary['60'],
    'primary-500': primary['50'],
    'primary-600': primary['40'],
    'primary-700': primary['30'],
    'primary-800': primary['20'],
    'primary-900': dark ? primary['5'] : primary['10'],
    'primary-950': primary['5'],
    // For avatars: tones 30–40, where white text keeps 4.5:1 in both themes
    'secondary-600': p.secondary['40'],
    'secondary-700': p.secondary['30'],
    'tertiary-600': p.tertiary['40'],
    'tertiary-700': p.tertiary['30'],

    'background': s.background,
    'on-background': s.onBackground,
    'ground': dark ? s.surfaceContainerLowest : s.surfaceContainer,
    'surface': dark ? s.surfaceContainerLow : s.surfaceContainerLowest,
    'on-surface': s.onSurface,
    'surface-bright': s.surfaceBright,
    'surface-light': s.surfaceContainerHigh,
    // Vuetify draws snackbars and its tooltips on surface-variant: the inverse surface in M3
    'surface-variant': s.inverseSurface,
    'on-surface-variant': s.inverseOnSurface,

    'primary': s.primary,
    'on-primary': s.onPrimary,
    'primary-container': s.primaryContainer,
    'on-primary-container': s.onPrimaryContainer,
    'secondary': s.secondary,
    'on-secondary': s.onSecondary,
    'secondary-container': s.secondaryContainer,
    'on-secondary-container': s.onSecondaryContainer,
    'tertiary': s.tertiary,
    'on-tertiary': s.onTertiary,
    'tertiary-container': s.tertiaryContainer,
    'on-tertiary-container': s.onTertiaryContainer,

    // Neutral scale (Tailwind surface-0 … 900): fills, borders, then text
    'surface-0': dark ? s.surfaceContainerLow : s.surfaceContainerLowest,
    'surface-50': dark ? s.surfaceContainer : s.surfaceContainerLow,
    'surface-100': dark ? s.surfaceContainerHigh : s.surfaceContainer,
    'surface-200': s.surfaceContainerHighest,
    'surface-300': s.outlineVariant,
    'surface-500': s.outline,
    'surface-600': s.onSurfaceVariant,
    'surface-700': dark ? nv['90'] : nv['20'],
    'surface-900': s.onSurface,

    'info': s.primary,
    'on-info': s.onPrimary,
    'info-container': s.primaryContainer,
    'on-info-container': s.onPrimaryContainer,
    'error': s.error,
    'on-error': s.onError,
    'error-container': s.errorContainer,
    'on-error-container': s.onErrorContainer,
  }
}

function channel (hex: string, i: number): number {
  const c = Number.parseInt(hex.slice(1 + i * 2, 3 + i * 2), 16) / 255
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
}

/** WCAG 2.x contrast ratio of two #RRGGBB colours. */
export function contrast (a: string, b: string): number {
  const lum = (hex: string) => 0.2126 * channel(hex, 0) + 0.7152 * channel(hex, 1) + 0.0722 * channel(hex, 2)
  const [la, lb] = [lum(a), lum(b)]
  const [hi, lo] = la > lb ? [la, lb] : [lb, la]
  return (hi + 0.05) / (lo + 0.05)
}

/** Text pairs the app relies on, with the 4.5:1 they need (WCAG 1.4.3); the editor warns on each. */
export function contrastProblems (theme: MaterialTheme): string[] {
  const problems: string[] = []
  for (const dark of [false, true]) {
    const c = materialColors(theme, dark)
    const label = dark ? 'Dark' : 'Light'
    const pairs: [string, string, string][] = [
      ['on-surface', 'surface', 'text on tiles'],
      ['surface-600', 'surface', 'secondary text on tiles'],
      ['on-primary', 'primary', 'text on primary buttons'],
      ['primary', 'surface', 'links and outlined buttons'],
      ['on-error-container', 'surface', 'field errors'],
    ]
    for (const [fg, bg, what] of pairs) {
      const ratio = contrast(c[fg]!, c[bg]!)
      if (ratio < 4.5) {
        problems.push(`${label}: ${what} is ${ratio.toFixed(1)}:1, under 4.5:1.`)
      }
    }
  }
  return problems
}
