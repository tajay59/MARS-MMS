import type { ThemePreference } from '@/app/theme/preference'
import { storeToRefs } from 'pinia'
import { useSessionStore } from '@/stores/session'
import { useThemeStore } from '@/stores/theme'

/** Light / Dark / System: applied at once, then saved on the account when signed in (DBD D2). */
export function useAppearance () {
  const theme = useThemeStore()
  const session = useSessionStore()
  const { preference } = storeToRefs(theme)

  async function choose (value: ThemePreference): Promise<void> {
    theme.setPreference(value)
    if (session.user && session.user.theme !== value) {
      try {
        await session.updateProfile({ theme: value })
      } catch {
        // Offline: the choice still applies on this device and is saved next time
      }
    }
  }

  return { preference, choose }
}
