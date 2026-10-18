import type { ThemePreference } from '@/app/theme/preference'
import type { ThemeInstance } from 'vuetify'
import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  darkQuery,
  readStoredPreference,
  resolveTheme,
  writeStoredPreference,
} from '@/app/theme/preference'

/*
  Switches Vuetify’s theme and the .app-dark class on <html> together (TRD §13.2).
  The preference is cached on the device for the login pages and saved on the account
  (PATCH /api/v1/auth/me, through useAppearance). At sign-in the account’s value wins: adopt().
*/
const PREFERENCES: ReadonlySet<ThemePreference> = new Set(['light', 'dark', 'system'])

export const useThemeStore = defineStore('theme', () => {
  const preference = ref<ThemePreference>(readStoredPreference())
  let vuetifyTheme: ThemeInstance | null = null

  function apply (): void {
    const name = resolveTheme(preference.value)
    vuetifyTheme?.change(name)
    document.documentElement.classList.toggle('app-dark', name === 'dark')
  }

  function init (theme: ThemeInstance): void {
    vuetifyTheme = theme
    apply()
    // "System" follows the device setting live
    window.matchMedia(darkQuery).addEventListener('change', () => {
      if (preference.value === 'system') {
        apply()
      }
    })
  }

  function setPreference (value: ThemePreference): void {
    preference.value = value
    writeStoredPreference(value)
    apply()
  }

  /** Take the signed-in account's setting (DBD D2). Ignores anything unexpected. */
  function adopt (value: string | null | undefined): void {
    if (value && PREFERENCES.has(value as ThemePreference)) {
      setPreference(value as ThemePreference)
    }
  }

  return { preference, init, setPreference, adopt }
})
