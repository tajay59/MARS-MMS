import { defineStore } from 'pinia'
import { ref } from 'vue'
import { usersApi } from '@/api/auth'

const CAP = 99

/** How many registrations wait for an admin: the sidebar badge (AFD J1 step 3). */
export const useRegistrationsStore = defineStore('registrations', () => {
  const pending = ref<number | null>(null)

  async function refresh (): Promise<void> {
    try {
      const page = await usersApi.list({ status: 'pending', limit: CAP + 1 })
      pending.value = page.items.length
    } catch {
      // The badge is a hint; the Registrations page shows the real list or its error
    }
  }

  function label (): string | null {
    if (!pending.value) {
      return null
    }
    return pending.value > CAP ? `${CAP}+` : String(pending.value)
  }

  return { pending, refresh, label }
})
