import type { Ref } from 'vue'
import { computed } from 'vue'

export const MIN_PASSWORD = 10

/** The live rule under a new-password field (AUTH-1: 10 or more characters). */
export function usePasswordRule (password: Ref<string>, serverError: Ref<string | undefined>) {
  const long = computed(() => password.value.length >= MIN_PASSWORD)
  const hint = computed(() => long.value ? `${MIN_PASSWORD} or more characters` : `Use at least ${MIN_PASSWORD} characters`)
  /** Shown as an error after a submit attempt, or the server's answer (breached, too long). */
  function error (submitted: boolean): string | undefined {
    if (serverError.value) {
      return serverError.value
    }
    return submitted && !long.value ? `Use at least ${MIN_PASSWORD} characters` : undefined
  }
  return { long, hint, error }
}
