import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useOnline } from '@/app/composables/useOnline'
import { useSessionStore } from '@/stores/session'

/*
  Whether a record page should read the phone's copy instead of asking the server: unlocked with
  the PIN and no token, or signed in but the radio says there is no connection (W13-13). A
  `record` is the :id in the address; the list and the forms always need the server.
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
  return { offline, id, showCopy: computed(() => offline.value && id.value !== null) }
}
