// The user's Light / Dark / System choice (DBD D2). public/theme-init.js mirrors this logic.

export type ThemePreference = 'light' | 'dark' | 'system'
export type ThemeName = 'light' | 'dark'

export const THEME_STORAGE_KEY = 'mms-theme'

export function readStoredPreference (): ThemePreference {
  try {
    const value = localStorage.getItem(THEME_STORAGE_KEY)
    return value === 'light' || value === 'dark' ? value : 'system'
  } catch {
    return 'system'
  }
}

export function writeStoredPreference (preference: ThemePreference): void {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, preference)
  } catch {
    // Storage blocked: the choice still applies for this session
  }
}

export const darkQuery = '(prefers-color-scheme: dark)'

export function resolveTheme (preference: ThemePreference): ThemeName {
  if (preference === 'system') {
    return window.matchMedia(darkQuery).matches ? 'dark' : 'light'
  }
  return preference
}
