<template>
  <PageBody>
    <div class="flex grow flex-col">
      <div class="flex grow flex-col gap-6 px-4 py-6 md:mx-auto md:w-full md:max-w-xl md:px-6">
        <div class="flex items-center gap-4" role="status">
          <div class="flex size-14 shrink-0 items-center justify-center rounded-full bg-success-container">
            <v-icon class="text-success" :icon="mdiCheck" size="32" />
          </div>

          <div>
            <p class="m-0 text-2xl font-semibold leading-8 text-surface-900">All synced</p>
            <p class="m-0 text-surface-900">{{ checkedAt ? `Nothing is waiting on this phone. Checked ${checkedAt}.` : 'Nothing is waiting on this phone.' }}</p>
          </div>
        </div>

        <FeedbackBanner v-if="offline" type="warning">No connection. Your work is safe on this phone and syncs when you have signal.</FeedbackBanner>

        <FeedbackBanner v-if="lowSpace" type="warning">
          Less than 1 GB free on this phone. Free some space before recording videos.
        </FeedbackBanner>

        <section aria-labelledby="storage-h" class="flex flex-col gap-3 rounded-card border border-surface-200 bg-surface p-4">
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

        <section aria-labelledby="appearance-h" class="mt-auto flex flex-col gap-3">
          <h2 id="appearance-h" class="m-0 text-h3 text-surface-900">Appearance</h2>
          <AppearanceToggle labelledby="appearance-h" :large="mobile" />
        </section>
      </div>

      <!-- Sticky action bar above the bottom navigation (DBD field shell) -->
      <div class="sticky bottom-0 bg-surface px-4 py-3 shadow-[0_-8px_24px_rgb(15_23_42/0.12)] md:static md:mx-auto md:w-full md:max-w-xl md:bg-transparent md:px-6 md:shadow-none">
        <v-btn
          block
          class="text-field-action"
          color="primary"
          :height="48"
          :loading="checking"
          @click="syncNow"
        >Sync now</v-btn>
      </div>
    </div>
  </PageBody>
</template>

<script lang="ts" setup>
  import { mdiCheck } from '@mdi/js'
  import { onMounted, ref } from 'vue'
  import { useDisplay } from 'vuetify'
  import { refreshSession } from '@/app/auth/session'
  import AppearanceToggle from '@/components/AppearanceToggle.vue'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import PageBody from '@/components/PageBody.vue'

  /*
    /sync (AFD §3, F3). Nothing is queued on a device until offline visits arrive in Phase 5, so
    "Sync now" only checks that the server can be reached. Storage figures are real: the quota,
    the 1 GB warning (TRD §7.1, R4) and whether the browser has persisted the app’s data.
  */
  const GB = 1024 ** 3
  const { mobile } = useDisplay()

  const storage = ref<{ used: number, free: number, percent: number, persisted: boolean } | null>(null)
  const lowSpace = ref(false)
  const offline = ref(false)
  const checking = ref(false)
  const checkedAt = ref<string | null>(null)

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

  async function syncNow (): Promise<void> {
    checking.value = true
    const result = await refreshSession()
    offline.value = result.kind === 'offline'
    checkedAt.value = offline.value
      ? null
      : new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(new Date())
    await measure()
    checking.value = false
  }

  onMounted(() => {
    void measure()
  })
</script>
