<template>
  <section aria-labelledby="diag-h" class="flex flex-col gap-1 rounded-card bg-surface-50 p-4">
    <h2 id="diag-h" class="m-0 mb-2 text-h3 text-surface-900">This phone</h2>

    <dl class="m-0 flex flex-col text-sm">
      <div v-for="row in rows" :key="row.label" class="flex items-center justify-between gap-4 border-b border-surface-200 py-2 last:border-b-0">
        <dt class="text-surface-600">{{ row.label }}</dt>
        <dd class="m-0 text-right" :class="[row.tone === 'good' ? 'font-semibold text-on-success-container' : row.tone === 'warn' ? 'font-semibold text-on-warning-container' : 'text-surface-900', row.mono ? 'font-mono' : '']">{{ row.value }}</dd>
      </div>
    </dl>

    <p v-if="storage && !storage.persisted" class="m-0 pt-2 text-sm text-surface-600">
      The browser may clear this app’s data if the phone runs short of space. Sync as soon as you have signal, and keep the app installed.
    </p>

    <div class="mt-3 flex flex-wrap gap-2">
      <v-btn :to="{ name: 'storage-check' }" variant="outlined">Storage check</v-btn>
      <v-btn :loading="copying" variant="outlined" @click="copyReport">Copy report</v-btn>
    </div>

    <p v-if="copied" class="m-0 pt-2 text-sm text-surface-600" role="status">Copied. Paste it into a message to the office.</p>

    <template v-if="reportText">
      <p class="m-0 pt-2 text-sm text-surface-600" role="status">This phone would not copy it. Select the text below and copy it by hand.</p>

      <v-textarea
        ref="reportBox"
        auto-grow
        class="font-mono"
        density="compact"
        hide-details
        label="Report"
        :model-value="reportText"
        readonly
        rows="6"
        @focus="selectAll"
      />
    </template>
  </section>
</template>

<script lang="ts" setup>
  import type { StorageReport } from '@/offline/storage'
  import { computed, nextTick, onMounted, ref } from 'vue'
  import { APP_VERSION } from '@/app/brand'
  import { useLiveQuery } from '@/app/composables/useLiveQuery'
  import { describePhone, isStandalone } from '@/app/pwa/platform'
  import { db, deviceId } from '@/offline/db'
  import { collectReport, formatReport } from '@/offline/report'
  import { offlineState, type OfflineState } from '@/offline/session'
  import { storageReport } from '@/offline/storage'
  import { useSessionStore } from '@/stores/session'

  // What a person (or the developer reading a bug report) needs to know about this phone: is the app
  // installed, will it open with no signal, will the browser keep its data, what is prepared and how
  // long the PIN lasts (W13-14, findings F3 and F14). Staff only; the page is.
  const session = useSessionStore()
  const storage = ref<StorageReport | null>(null)
  const pin = ref<OfflineState | null>(null)
  const device = ref('')
  const worker = ref<boolean | null>(null)
  const copying = ref(false)
  const copied = ref(false)
  const reportText = ref('')
  const reportBox = ref<{ $el: HTMLElement } | null>(null)

  const { value: prepared } = useLiveQuery(async () => {
    const id = session.user?.id
    if (!id) {
      return { visits: 0, files: 0 }
    }
    return {
      visits: await db.bundles.where('user_id').equals(id).count(),
      files: await db.files.where('user_id').equals(id).count(),
    }
  })

  const until = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short' })

  const rows = computed(() => {
    const out: { label: string, value: string, tone?: 'good' | 'warn', mono?: boolean }[] = [
      { label: 'App', value: `${isStandalone() ? 'Installed' : 'In the browser'} · version ${APP_VERSION}` },
      worker.value === null
        ? { label: 'Works with no signal', value: 'Checking…' }
        : { label: 'Works with no signal', value: worker.value ? 'Yes' : 'Not yet', tone: worker.value ? 'good' : 'warn' },
    ]
    if (storage.value) {
      out.push({ label: 'Data kept by the browser', value: storage.value.persisted ? 'Yes' : 'Not guaranteed', tone: storage.value.persisted ? 'good' : 'warn' })
    }
    const p = prepared.value
    out.push({ label: 'Prepared visits', value: p ? `${p.visits} · ${p.files} ${p.files === 1 ? 'file' : 'files'}` : '…' })
    if (pin.value) {
      out.push({ label: 'Offline PIN', value: pinText(pin.value) })
    }
    out.push({ label: 'Phone', value: describePhone() })
    if (device.value) {
      out.push({ label: 'Device ID', value: `${device.value.slice(0, 4)}…${device.value.slice(-4)}`, mono: true })
    }
    return out
  })

  function pinText (state: OfflineState): string {
    switch (state.kind) {
      case 'ready': {
        return `Set · valid to ${until.format(new Date(state.profile.offline_until))}`
      }
      case 'disabled': {
        return 'Turned off · log in with signal'
      }
      case 'expired': {
        return 'Ended · log in with signal'
      }
      default: {
        return 'Not set'
      }
    }
  }

  // Plain text a technician can paste into a message: versions, states, counts and the sync log,
  // never a token, a PIN or anything recorded (W15-4). Where the clipboard is refused, the text is
  // shown to select by hand.
  async function copyReport () {
    const id = session.user?.id
    if (!id) {
      return
    }
    copying.value = true
    copied.value = false
    reportText.value = ''
    try {
      const text = formatReport(await collectReport(id, APP_VERSION))
      try {
        await navigator.clipboard.writeText(text)
        copied.value = true
      } catch {
        reportText.value = text
      }
    } finally {
      copying.value = false
    }
  }

  async function selectAll () {
    await nextTick()
    reportBox.value?.$el.querySelector('textarea')?.select()
  }

  onMounted(async () => {
    storage.value = await storageReport().catch(() => null)
    pin.value = await offlineState().catch(() => null)
    device.value = await deviceId().catch(() => '')
    // A worker in control means the next start works with no signal (F14)
    worker.value = 'serviceWorker' in navigator ? Boolean(navigator.serviceWorker.controller) : false
  })
</script>
