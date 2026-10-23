import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useLiveQuery } from '@/app/composables/useLiveQuery'
import { useOnline } from '@/app/composables/useOnline'
import { db } from '@/offline/db'
import { useSessionStore } from '@/stores/session'

/*
  Whether a record page should read the phone's copy instead of asking the server: unlocked with
  the PIN and no token, or signed in but the radio says there is no connection (W13-13). A
  `record` is the :id in the address; the list and the forms always need the server.
  `kept` says whether the visit in the address is prepared on this phone (ready), which decides
  whether the field page can work from it (W14-6).
*/
export function useOfflineMode () {
  const session = useSessionStore()
  const route = useRoute()
  const online = useOnline()
  const offline = computed(() => session.offline || !online.value)
  const id = computed(() => {
    const value = route.params.id
    return typeof value === 'string' && value !== 'new' && !route.params.mode ? value : null
  })
  const { value: row } = useLiveQuery(async () => {
    const wanted = id.value
    return wanted ? ((await db.bundles.get(wanted)) ?? null) : null
  })
  /** undefined while it is being looked up; then true or false. */
  const kept = computed<boolean | undefined>(() => {
    if (row.value === undefined) {
      return undefined
    }
    return Boolean(row.value && row.value.user_id === session.user?.id && row.value.ready)
  })
  return { offline, id, kept, showCopy: computed(() => offline.value && id.value !== null) }
}
