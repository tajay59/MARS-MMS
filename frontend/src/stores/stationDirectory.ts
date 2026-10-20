import type { StationSummary } from '@/api/models'
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { stationsApi } from '@/api/operations'
import { onSessionChange } from '@/app/auth/session'

/*
  Every station the person may see, held in memory for the pages that need all of them at once
  (the map, the scanner's code field). Not stored on the device: what a phone keeps for use with
  no signal is a prepared visit's bundle (Phase 5, OFF-1), and a list kept here would outlive the
  login it was fetched under. It empties whenever the account changes or the session ends.
*/
export const useStationDirectory = defineStore('stationDirectory', () => {
  const stations = ref<StationSummary[]>([])
  const loaded = ref(false)
  const loading = ref(false)
  const error = ref<unknown>(null)
  let inFlight: Promise<void> | null = null
  let owner: string | null = null

  function clear (): void {
    stations.value = []
    loaded.value = false
    error.value = null
    inFlight = null
    owner = null
  }

  onSessionChange(session => {
    if (!session || session.user.id !== owner) {
      clear()
    }
  })

  /** Loads the list once per login; `force` loads it again. Failures keep what was loaded before. */
  function load (userId: string, force = false): Promise<void> {
    if (owner !== null && owner !== userId) {
      clear()
    }
    if (inFlight) {
      return inFlight
    }
    if (loaded.value && !force) {
      return Promise.resolve()
    }
    owner = userId
    loading.value = true
    error.value = null
    const run = (async () => {
      try {
        const all: StationSummary[] = []
        let after: string | undefined
        do {
          const page = await stationsApi.list({ limit: 500, after })
          all.push(...page.items)
          after = page.next_after ?? undefined
        } while (after)
        stations.value = all
        loaded.value = true
      } catch (error_) {
        error.value = error_
      } finally {
        loading.value = false
        inFlight = null
      }
    })()
    inFlight = run
    return run
  }

  return { stations, loaded, loading, error, load, clear }
})
