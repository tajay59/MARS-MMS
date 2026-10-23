import type { Concern } from '@/features/visits/local/attention'
import type { Totals, VisitPending } from '@/offline/pending'
import { computed } from 'vue'
import { useLiveQuery } from '@/app/composables/useLiveQuery'
import { concerns } from '@/features/visits/local/attention'
import { uploadsLabel } from '@/features/visits/uploadQueues'
import { pendingByVisit, totalsOf } from '@/offline/pending'
import { useSessionStore } from '@/stores/session'

/*
  What /sync and the badge show, straight from the phone's own database (OFF-6): visit by visit
  what is waiting, and the things that need the person. `undefined` until IndexedDB has answered,
  so a screen can show nothing yet rather than "All synced" by mistake.
*/
export function useSyncOverview () {
  const session = useSessionStore()
  const userId = (): string | null => session.user?.id ?? null
  const { value: pending } = useLiveQuery<VisitPending[]>(async () => {
    const id = userId()
    return id ? pendingByVisit(id) : []
  })
  const { value: stuck } = useLiveQuery<Concern[]>(async () => {
    const id = userId()
    return id ? concerns(id) : []
  })
  const ready = computed(() => pending.value !== undefined && stuck.value !== undefined)
  const totals = computed<Totals>(() => totalsOf(pending.value ?? [], stuck.value?.length ?? 0))
  return { pending, stuck, ready, totals }
}

/** The few words on the rail and the badge: what waits on the phone, from IndexedDB, or what is going up from memory. */
export function useSyncLabel () {
  const { totals } = useSyncOverview()
  return computed<string | null>(() => {
    const { changes, files, attention } = totals.value
    if (attention > 0) {
      return attention === 1 ? '1 needs you' : `${attention} need you`
    }
    if (changes + files > 0) {
      return `${changes + files} waiting`
    }
    return uploadsLabel.value
  })
}
