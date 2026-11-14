<template>
  <PageBody>
    <div class="flex grow flex-col">
      <div class="flex grow flex-col gap-6 px-4 py-6 md:mx-auto md:w-full md:max-w-xl md:px-6">
        <!-- The one-line answer: sending, waiting, log in, or done -->
        <div class="flex items-center gap-4" role="status">
          <div class="flex size-14 shrink-0 items-center justify-center rounded-full" :class="head.disc">
            <v-icon :icon="head.icon" size="32" />
          </div>

          <div>
            <p class="m-0 text-2xl font-semibold leading-8 text-surface-900">{{ head.title }}</p>
            <p class="m-0 text-surface-900">{{ head.text }}</p>
          </div>
        </div>

        <FeedbackBanner v-if="running" type="warning">
          Keep MARS-MMS open while it syncs.<template v-if="wakeLockSupported"> The screen stays on.</template> A phone stops sending when you leave the app.
        </FeedbackBanner>

        <FeedbackBanner v-else-if="offline" type="warning">No connection. Your work is safe on this phone and syncs when you have signal.</FeedbackBanner>
        <FeedbackBanner v-else-if="needsLogin" type="warning">Your session ended. Log in with signal and the sync carries on by itself.</FeedbackBanner>

        <FeedbackBanner v-if="lowSpace" type="warning">
          Less than 1 GB free on this phone. Free some space before recording videos.
        </FeedbackBanner>

        <!-- Visit by visit: what is waiting -->
        <section v-if="pending && pending.length > 0" aria-label="Visits waiting" class="flex flex-col gap-3 rounded-card bg-surface-50 p-4">
          <div v-for="visit in pending" :key="visit.visit_id" class="flex flex-col gap-2">
            <div class="flex items-baseline justify-between gap-2">
              <span class="font-mono text-sm font-medium text-surface-900" translate="no">{{ visit.ref }}</span>
              <span class="text-sm text-surface-600">{{ countsText(visit.changes, visit.files, running) }}</span>
            </div>

            <p v-if="visit.title" class="m-0 text-sm text-surface-700">{{ visit.title }}</p>
            <p v-if="visit.ending" class="m-0 text-sm text-surface-700">Your report is made once the visit has synced.</p>
          </div>

          <template v-if="running && progress.total > 0">
            <div
              aria-label="Progress"
              :aria-valuemax="100"
              :aria-valuemin="0"
              :aria-valuenow="progress.percent"
              class="h-2 overflow-hidden rounded bg-surface-100"
              role="progressbar"
            >
              <div class="h-2 bg-primary" :style="{ width: `${progress.percent}%` }" />
            </div>

            <p class="m-0 flex justify-between tabular-nums text-sm text-surface-700">
              <span>{{ size(progress.done) }} of {{ size(progress.total) }}</span><span>{{ progress.percent }}%</span>
            </p>
          </template>
        </section>

        <NeedsAttention v-if="stuck" :concerns="stuck" />

        <section aria-labelledby="storage-h" class="flex flex-col gap-3 rounded-card bg-surface-50 p-4">
          <h2 id="storage-h" class="m-0 text-h3 text-surface-900">Storage on this phone</h2>

          <template v-if="storage">
            <div
              aria-label="Storage used"
              aria-valuemax="100"
              aria-valuemin="0"
              :aria-valuenow="storage.percent"
              class="h-2 overflow-hidden rounded bg-surface-100"
              role="meter"
            >
              <div class="h-2 bg-primary" :style="{ width: `${Math.max(storage.percent, 1)}%` }" />
            </div>

            <p class="m-0 flex justify-between tabular-nums text-surface-900">
              <span>{{ size(storage.used) }} used</span><span>{{ size(storage.free) }} free</span>
            </p>

            <p class="m-0 text-sm text-surface-600">
              {{ storage.persisted ? 'The browser keeps this app’s data until you remove it.' : 'The browser may clear this app’s data if the phone runs short of space.' }}
            </p>
          </template>

          <p v-else class="m-0 text-sm text-surface-600">This browser doesn’t say how much space is left.</p>
        </section>

        <DiagnosticsCard v-if="isStaff" />

        <section aria-labelledby="appearance-h" class="mt-auto flex flex-col gap-3">
          <h2 id="appearance-h" class="m-0 text-h3 text-surface-900">Appearance</h2>
          <AppearanceToggle labelledby="appearance-h" :large="mobile" />
        </section>
      </div>

      <!-- Sticky action bar above the bottom navigation (DBD field shell) -->
      <div class="sticky bottom-0 bg-surface px-4 py-3 shadow-[0_-8px_24px_rgb(15_23_42/0.12)] md:static md:mx-auto md:w-full md:max-w-xl md:bg-transparent md:px-6 md:shadow-none">
        <v-btn
          v-if="needsLogin"
          block
          class="text-field-action"
          color="primary"
          :height="48"
          :to="{ name: 'login', query: { next: '/sync' } }"
        >Log in</v-btn>

        <v-btn
          v-else
          block
          class="text-field-action"
          :color="running ? undefined : 'primary'"
          :disabled="running"
          :height="48"
          :loading="checking && !running"
          @click="syncNowClick"
        >{{ running ? 'Syncing…' : 'Sync now' }}</v-btn>
      </div>
    </div>
  </PageBody>
</template>

<script lang="ts" setup>
  import { mdiCheck, mdiCloudOffOutline, mdiCloudUploadOutline, mdiLockOutline } from '@mdi/js'
  import { computed, onMounted, ref, watch } from 'vue'
  import { useDisplay } from 'vuetify'
  import { refreshSession } from '@/app/auth/session'
  import { useWakeLock, wakeLockSupported } from '@/app/pwa/wakeLock'
  import AppearanceToggle from '@/components/AppearanceToggle.vue'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import PageBody from '@/components/PageBody.vue'
  import { syncNow, syncStatus } from '@/features/visits/local/syncApp'
  import { uploadsLabel, uploadsOnTheirWay } from '@/features/visits/uploadQueues'
  import { useSessionStore } from '@/stores/session'
  import DiagnosticsCard from './DiagnosticsCard.vue'
  import NeedsAttention from './NeedsAttention.vue'
  import { useSyncOverview } from './useSyncOverview'

  /*
    /sync (AFD §3, F3, F12; W14). The counts come from IndexedDB, so they are right with no signal:
    what waits, visit by visit, and what needs the person. "Sync now" runs the sync runner at once
    (the same one that runs by itself) and the screen stays on while it works. Storage figures are
    real: the quota, the 1 GB warning (TRD §7.1, R4) and whether the browser has persisted the
    app’s data.
  */
  const GB = 1024 ** 3
  const { mobile } = useDisplay()
  const { isStaff } = useSessionStore()
  const { pending, stuck, totals, ready } = useSyncOverview()

  const storage = ref<{ used: number, free: number, percent: number, persisted: boolean } | null>(null)
  const lowSpace = ref(false)
  const checking = ref(false)
  const checkedAt = ref<string | null>(null)
  const offlineNow = ref(false)

  const running = computed(() => syncStatus.running)
  const needsLogin = computed(() => syncStatus.last?.outcome === 'login' && totals.value.changes + totals.value.files > 0)
  const offline = computed(() => offlineNow.value || syncStatus.last?.outcome === 'offline')
  const waiting = computed(() => totals.value.changes + totals.value.files)

  useWakeLock(running)

  // How far the files have gone: bytes still on the phone against what was there when the run began
  const startBytes = ref(0)
  watch(running, on => {
    if (on) {
      startBytes.value = totals.value.bytes
    }
  })
  const progress = computed(() => {
    const total = Math.max(startBytes.value, totals.value.bytes)
    const done = Math.max(total - totals.value.bytes, 0)
    return { total, done, percent: total > 0 ? Math.min(Math.round((done / total) * 100), 100) : 0 }
  })

  function countsText (changes: number, files: number, left: boolean): string {
    const parts = [
      changes > 0 ? `${changes} ${changes === 1 ? 'change' : 'changes'}${left ? ' left' : ''}` : '',
      files > 0 ? `${files} ${files === 1 ? 'file' : 'files'}${left ? ' left' : ''}` : '',
    ]
    return parts.filter(Boolean).join(' · ')
  }

  function plural (count: number, one: string, many: string): string {
    return `${count} ${count === 1 ? one : many}`
  }

  const head = computed(() => {
    const { changes, files, attention } = totals.value
    const lists = [changes > 0 ? plural(changes, 'change', 'changes') : '', files > 0 ? plural(files, 'file', 'files') : ''].filter(Boolean).join(' and ')
    if (!ready.value) {
      return { disc: 'bg-surface-100', icon: mdiCloudUploadOutline, title: 'Checking this phone', text: 'Looking at what is waiting.' }
    }
    if (running.value) {
      return { disc: 'bg-primary-100 dark:bg-primary-800 text-primary', icon: mdiCloudUploadOutline, title: 'Sending your work', text: lists ? `${lists} on their way.` : 'Almost done.' }
    }
    if (needsLogin.value) {
      return { disc: 'bg-warning-container text-warning', icon: mdiLockOutline, title: 'Log in to finish syncing', text: `Your work is saved on this phone. ${lists} ${waiting.value === 1 ? 'is' : 'are'} waiting.` }
    }
    if (attention > 0) {
      return {
        disc: 'bg-error-container text-error',
        icon: mdiCloudOffOutline,
        title: attention === 1 ? '1 thing needs you' : `${attention} things need you`,
        text: waiting.value > 0 ? `${lists} ${waiting.value === 1 ? 'is' : 'are'} waiting behind ${attention === 1 ? 'it' : 'them'}.` : 'Everything else is synced.',
      }
    }
    if (waiting.value > 0) {
      return {
        disc: 'bg-warning-container text-warning',
        icon: offline.value ? mdiCloudOffOutline : mdiCloudUploadOutline,
        title: `${lists} waiting`,
        text: offline.value ? 'No connection. Your work is safe on this phone and goes up when you have signal.' : 'Your work is safe on this phone and goes up by itself. Sync now sends it at once.',
      }
    }
    if (uploadsLabel.value) {
      // Files for a visit that is not kept on this phone go up from memory, with the app open
      return {
        disc: uploadsOnTheirWay.value.sending > 0 ? 'bg-primary-100 dark:bg-primary-800 text-primary' : 'bg-warning-container text-warning',
        icon: mdiCloudUploadOutline,
        title: uploadsLabel.value,
        text: uploadsOnTheirWay.value.sending > 0 ? 'Photos and video for your visits. Keep the app open until they finish.' : 'Open the visit and try again from the file.',
      }
    }
    return {
      disc: 'bg-success-container text-success',
      icon: mdiCheck,
      title: 'All synced',
      text: checkedAt.value ? `Nothing is waiting on this phone. Checked ${checkedAt.value}.` : 'Nothing is waiting on this phone.',
    }
  })

  function size (bytes: number): string {
    if (bytes >= GB) {
      return `${(bytes / GB).toFixed(1)} GB`
    }
    return `${Math.max(1, Math.round(bytes / 1024 ** 2))} MB`
  }

  async function measure (): Promise<void> {
    if (!navigator.storage?.estimate) {
      return
    }
    const { usage = 0, quota = 0 } = await navigator.storage.estimate()
    const persisted = navigator.storage.persisted ? await navigator.storage.persisted() : false
    const free = Math.max(quota - usage, 0)
    storage.value = { used: usage, free, percent: quota ? Math.round((usage / quota) * 100) : 0, persisted }
    lowSpace.value = quota > 0 && free < GB
  }

  async function syncNowClick (): Promise<void> {
    checking.value = true
    offlineNow.value = false
    try {
      const result = await syncNow(true)
      if (result === null) {
        // Not signed in with a token, or no connection: the plain check says which
        const session = await refreshSession()
        offlineNow.value = session.kind === 'offline'
      } else if (result.outcome === 'offline') {
        offlineNow.value = true
      }
      checkedAt.value = offlineNow.value
        ? null
        : new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(new Date())
      await measure()
    } finally {
      checking.value = false
    }
  }

  onMounted(() => {
    void measure()
  })
</script>
