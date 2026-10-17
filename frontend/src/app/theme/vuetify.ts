import { createVuetify } from 'vuetify'
import { aliases, mdi } from 'vuetify/iconsets/mdi-svg'
import { buildThemes, builtInMaterial } from './brand'
import { readCachedBranding } from './brandingCache'
import { readStoredPreference, resolveTheme } from './preference'
import 'vuetify/styles'

/*
  The one createVuetify call (TRD §13.2). Global defaults give the DBD look, so pages don’t
  repeat props: flat 40 px buttons with a 6 px radius, outlined compact inputs, flat cards with
  a 1 px border and 10 px radius, no ripple. The field shell raises sizes to 48 px with a
  VDefaultsProvider. rounded="md" / "card" resolve to Tailwind’s rounded-md / rounded-card.
*/

// hideDetails 'auto': room for a hint or error only when there is one, so forms keep a 16 px rhythm
// The organization's colours as last fetched, so the first paint is already in them (W4-12)
const initial = buildThemes(readCachedBranding().material ?? builtInMaterial)

const input = { variant: 'outlined', density: 'compact', rounded: 'md', hideDetails: 'auto' } as const

export default createVuetify({
  theme: {
    defaultTheme: resolveTheme(readStoredPreference()),
    utilities: false,
    themes: {
      light: initial.light,
      dark: initial.dark,
    },
  },
  icons: {
    defaultSet: 'mdi',
    aliases,
    sets: { mdi },
  },
  display: {
    mobileBreakpoint: 'md',
    thresholds: {
      xs: 0,
      sm: 640,
      md: 768,
      lg: 1024,
      xl: 1280,
      xxl: 1536,
    },
  },
  defaults: {
    global: {
      ripple: false,
    },
    VBtn: {
      variant: 'flat',
      height: 40,
      rounded: 'md',
    },
    VTextField: input,
    VTextarea: input,
    VSelect: input,
    VAutocomplete: input,
    VCombobox: input,
    VCard: {
      flat: true,
      rounded: 'card',
      class: 'border border-surface-200',
    },
  },
})
