import type { BundleFile, FieldBundle, VisitOut } from '@/api/models'
import type { Progress, Source } from '@/offline/bundles'
import type { Ref } from 'vue'
import Dexie from 'dexie'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { mediaApi } from '@/api/media'
import { configVersionsApi, documentsApi, visitsApi } from '@/api/operations'
import { ApiError, NetworkError } from '@/api/problem'
import { currentSession } from '@/app/auth/session'
import { useLiveQuery } from '@/app/composables/useLiveQuery'
import { useOnline } from '@/app/composables/useOnline'
import { formatBytes } from '@/features/stations/documents'
import { userHasPin } from '@/offline/account'
import { BundleTooNew, prepareVisit, readBlob } from '@/offline/bundles'
import { db, deviceId } from '@/offline/db'
import { requestPersistence } from '@/offline/storage'
import { useSessionStore } from '@/stores/session'

/*
  Prepare for field on the visit page (OFF-1, AFD J5 step 4, W13-9 to W13-14). The engine is
  offline/bundles.ts; this adds the choice of documents, the PIN the first time, the download's
  progress and what the person is told when it stops.
*/

/** Documents up to this size start ticked (question 1, 2026-10-22). */
const TICKED_UP_TO = 10 * 1024 * 1024
/** Over this on a metered link, ask first (W13-14). */
const ASK_ABOVE = 100 * 1024 * 1024

export interface Choice {
  media_id: string
  name: string
  size: number
  station_id: string
}

interface ConnectionInfo { saveData?: boolean, type?: string }

function metered (): boolean {
  const connection = (navigator as Navigator & { connection?: ConnectionInfo }).connection
  return Boolean(connection?.saveData) || connection?.type === 'cellular'
}

/**
 A visit with dozens of documents asks for dozens of links in a few seconds, and the gateway
 answers 429 past its rate: wait and ask again (1 s, 2 s, 4 s) rather than give the file up.
*/
async function patiently<T> (ask: () => Promise<T>, signal?: AbortSignal): Promise<T> {
  for (let attempt = 0; ; attempt++) {
    try {
      return await ask()
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 429 || attempt >= 3) {
        throw error
      }
      await new Promise(resolve => setTimeout(resolve, 1000 * 2 ** attempt))
      signal?.throwIfAborted()
    }
  }
}

/** The server's links for one file, and the bytes behind them. */
const source: Source = {
  bundle: (visitId, device, signal) => visitsApi.fieldBundle(visitId, device, signal),
  link: async (file: BundleFile, signal) => {
    if (file.kind === 'config') {
      const media = await patiently(() => mediaApi.get(file.media_id, signal), signal)
      const url = media.urls?.download
      if (!url) {
        throw new Error('no link')
      }
      return url
    }
    return (await patiently(() => documentsApi.download(file.document_id!, false), signal)).url
  },
  download: async (url, onBytes, signal) => {
    const response = await fetch(url, { signal })
    if (!response.ok) {
      throw new Error(`The file server answered ${response.status}`)
    }
    return readBlob(response, onBytes)
  },
}

export function usePrepare (visit: Ref<VisitOut>) {
  const session = useSessionStore()
  const online = useOnline()
  const visitId = visit.value.id

  const { value: row } = useLiveQuery(async () => (await db.bundles.get(visitId)) ?? null)
  const { value: stored } = useLiveQuery(() =>
    db.files.where('[visit_id+media_id]').between([visitId, Dexie.minKey], [visitId, Dexie.maxKey]).toArray())

  const choices = ref<Choice[]>([])
  const configFiles = ref({ count: 0, size: 0 })
  const ticked = ref(new Set<string>())
  const loadingChoices = ref(false)

  const running = ref(false)
  const progress = ref<Progress | null>(null)
  const failure = ref('')
  const missing = ref<BundleFile[]>([])
  const askingPin = ref(false)
  const askingMobileData = ref(false)
  let controller: AbortController | null = null
  let wakeLock: WakeLockSentinel | null = null

  const mine = computed(() => (row.value && row.value.user_id === session.user?.id ? row.value : null))
  const loading = computed(() => row.value === undefined)
  const bundleData = computed(() => (mine.value?.data ?? null) as FieldBundle | null)

  const state = computed<'none' | 'incomplete' | 'ready'>(() => {
    if (!mine.value) {
      return 'none'
    }
    return mine.value.ready ? 'ready' : 'incomplete'
  })

  /** Documents the bundle listed and the phone does not have (after a partial run). */
  const gaps = computed<BundleFile[]>(() => {
    if (!mine.value || !stored.value) {
      return []
    }
    const have = new Set(stored.value.map(f => f.media_id))
    const chosen = new Set(mine.value.documents)
    return (bundleData.value?.files ?? []).filter(f => !have.has(f.media_id) && (f.required || chosen.has(f.media_id)))
  })

  const storedBytes = computed(() => (stored.value ?? []).reduce((sum, f) => sum + f.size, 0))

  /** The visit moved on since it was prepared: another owner, new dates, a cancel. */
  const changed = computed(() => {
    const prepared = bundleData.value?.visit
    return Boolean(prepared && visit.value.version > prepared.version)
  })

  const estimate = computed(() => {
    const documents = choices.value.filter(c => ticked.value.has(c.media_id)).reduce((sum, c) => sum + c.size, 0)
    return documents + configFiles.value.size
  })

  async function loadChoices (): Promise<void> {
    if (!online.value) {
      return
    }
    loadingChoices.value = true
    try {
      const found = new Map<string, Choice>()
      let config = { count: 0, size: 0 }
      for (const station of visit.value.stations) {
        const docs = await documentsApi.forStation(station.station_id)
        for (const d of [...docs.station, ...docs.models.flatMap(m => m.documents)]) {
          if (d.media_id && d.status === 'available' && !found.has(d.media_id)) {
            found.set(d.media_id, { media_id: d.media_id, name: d.filename, size: d.size_bytes, station_id: station.station_id })
          }
        }
        const [latest] = await configVersionsApi.list(station.station_id)
        if (latest) {
          config = { count: config.count + latest.files.length, size: config.size + latest.files.reduce((s, f) => s + f.size_bytes, 0) }
        }
      }
      choices.value = [...found.values()]
      configFiles.value = config
    } catch {
      // The panel works without the list; Prepare still downloads the configuration files
    } finally {
      loadingChoices.value = false
    }
  }

  /*
    What starts ticked: the documents chosen last time when the visit is already prepared (so
    "Update offline copy" does not bring back what was left out), else the small ones. Until the
    person ticks something themselves.
  */
  let touched = false
  function startingTicks (): Set<string> {
    return mine.value
      ? new Set(mine.value.documents)
      : new Set(choices.value.filter(c => c.size <= TICKED_UP_TO).map(c => c.media_id))
  }
  watch([mine, choices, loading], () => {
    if (!touched && !loading.value) {
      ticked.value = startingTicks()
    }
  }, { immediate: true })

  function toggle (mediaId: string, on: boolean): void {
    touched = true
    const next = new Set(ticked.value)
    if (on) {
      next.add(mediaId)
    } else {
      next.delete(mediaId)
    }
    ticked.value = next
  }

  /** The first press: a PIN if the phone has none, a word about mobile data, then the download. */
  async function start (): Promise<void> {
    failure.value = ''
    const me = session.user
    if (!me || running.value) {
      return
    }
    if (!(await userHasPin(me.id))) {
      askingPin.value = true
      return
    }
    if (metered() && estimate.value > ASK_ABOVE && !askingMobileData.value) {
      askingMobileData.value = true
      return
    }
    askingMobileData.value = false
    await run()
  }

  async function run (): Promise<void> {
    const me = session.user
    if (!me) {
      return
    }
    running.value = true
    missing.value = []
    controller = new AbortController()
    progress.value = { filesDone: 0, filesTotal: 0, bytesDone: 0, bytesTotal: 0, current: null }
    try {
      await requestPersistence()
      wakeLock = await navigator.wakeLock?.request('screen').catch(() => null) ?? null
      const outcome = await prepareVisit(source, {
        visitId,
        userId: me.id,
        deviceId: await deviceId(),
        documents: ticked.value,
        signal: controller.signal,
        onProgress: p => {
          progress.value = p
        },
      })
      missing.value = outcome.missing
      if (!outcome.ready) {
        failure.value = 'The configuration files did not all arrive. Try again.'
      }
    } catch (error) {
      failure.value = explain(error)
    } finally {
      running.value = false
      progress.value = null
      controller = null
      await wakeLock?.release().catch(() => undefined)
      wakeLock = null
    }
  }

  function stop (): void {
    controller?.abort()
  }

  function explain (error: unknown): string {
    if (error instanceof BundleTooNew) {
      return 'Update the app, then prepare again.'
    }
    if (error instanceof DOMException && error.name === 'QuotaExceededError') {
      return 'This phone is out of space. Free some space, then try again.'
    }
    if (error instanceof DOMException && error.name === 'AbortError') {
      return 'Stopped. What already arrived is kept.'
    }
    if (error instanceof ApiError) {
      if (error.status === 403) {
        return 'Only the people attending this visit can prepare it.'
      }
      if (error.code === 'visit_not_preparable') {
        return 'This visit has ended or been cancelled, so it cannot be prepared.'
      }
    }
    if (error instanceof NetworkError || error instanceof TypeError) {
      return 'The connection dropped. What already arrived is kept. Try again.'
    }
    return 'Something went wrong. Try again in a minute.'
  }

  /** The PIN was saved: carry on with the download. */
  async function pinSaved (): Promise<void> {
    askingPin.value = false
    if (currentSession()) {
      await start()
    }
  }

  onMounted(loadChoices)
  watch(online, isOnline => {
    if (isOnline && choices.value.length === 0) {
      void loadChoices()
    }
  })
  onBeforeUnmount(stop)

  return {
    online, loading, state, row: mine, stored, choices, configFiles, ticked, loadingChoices,
    running, progress, failure, missing, gaps, changed, estimate, storedBytes,
    askingPin, askingMobileData, bytes: formatBytes,
    toggle, start, run, stop, pinSaved,
  }
}
