<template>
  <section aria-labelledby="qr-h" class="flex flex-col gap-3">
    <h2 id="qr-h" class="m-0 text-h3 text-surface-900">QR label</h2>

    <div class="grid grid-cols-[auto_minmax(0,1fr)] items-center gap-4">
      <div v-if="!picture" aria-label="Drawing the QR code…" class="size-30 rounded-md border border-surface-200 bg-surface-100" role="status" />

      <svg
        v-else
        :aria-label="`QR code for ${station.name}`"
        class="size-30 rounded-md border border-surface-200 bg-white p-1.5 text-black"
        role="img"
        shape-rendering="crispEdges"
        :viewBox="`${-QUIET} ${-QUIET} ${picture.size + QUIET * 2} ${picture.size + QUIET * 2}`"
      >
        <rect
          fill="#fff"
          :height="picture.size + QUIET * 2"
          width="100%"
          :x="-QUIET"
          :y="-QUIET"
        />

        <path :d="picture.path" fill="currentColor" />
      </svg>

      <div class="flex min-w-0 flex-col gap-2.5">
        <p class="m-0 text-sm text-surface-600">
          Opens
          <span class="block break-all font-mono text-surface-900" translate="no">{{ shortScanUrl(origin, token) }}</span>
        </p>

        <p v-if="replaced" class="m-0 text-sm font-medium text-on-success-container" role="status">Replaced just now. Print the new label.</p>

        <div v-if="isAdmin" class="flex flex-wrap gap-2">
          <v-btn :prepend-icon="mdiPrinterOutline" size="small" :to="{ name: 'admin-stations-tools', query: { station: station.id } }" variant="tonal">Print this label</v-btn>
          <v-btn :prepend-icon="mdiRefresh" size="small" variant="outlined" @click="ask">Replace the label</v-btn>
        </div>
      </div>
    </div>

    <p class="m-0 text-sm text-surface-600">The code holds only a random token, never station data, so a lost label shows nothing to a stranger.</p>

    <ModalSheet v-model="confirming" labelledby="qr-replace-h" :max-width="460" :persistent="busy">
      <h2 id="qr-replace-h" class="m-0 mb-4 text-h2 text-surface-900">Replace the label for {{ station.name }}?</h2>

      <FeedbackBanner type="warning">
        <strong>The label on the station will stop working.</strong> Scanning it will say the code is no longer valid until the new label is stuck on.
      </FeedbackBanner>

      <p class="mb-0 mt-4 text-surface-600">Replace it when a label is lost, damaged or photographed where it shouldn’t be. Nothing else about the station changes.</p>

      <FeedbackBanner v-if="error" class="mt-4" type="error">{{ error }}</FeedbackBanner>

      <div class="mt-6 flex flex-wrap justify-end gap-2">
        <v-btn :disabled="busy" variant="text" @click="confirming = false">Cancel</v-btn>
        <v-btn color="error" :loading="busy" @click="replace">Replace the label</v-btn>
      </div>
    </ModalSheet>
  </section>
</template>

<script lang="ts" setup>
  import type { QrPicture } from './qrCode'
  import type { StationDetail } from '@/api/models'
  import { mdiPrinterOutline, mdiRefresh } from '@mdi/js'
  import { storeToRefs } from 'pinia'
  import { ref, shallowRef, watch } from 'vue'
  import { qrApi } from '@/api/operations'
  import { NetworkError } from '@/api/problem'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import ModalSheet from '@/components/ModalSheet.vue'
  import { scanUrl, shortScanUrl } from '@/features/scan/scan'
  import { useSessionStore } from '@/stores/session'

  // The station's label (PRD QR-1, QR-7), on the Overview tab for staff. Only admins replace it:
  // the old label stops working at once. The server leaves the token out for clients.
  const props = defineProps<{ station: StationDetail, token: string }>()
  const emit = defineEmits<{ replaced: [station: StationDetail] }>()

  const QUIET = 2 // modules of white around the code, beside the 6 px of padding
  const { isAdmin } = storeToRefs(useSessionStore())
  const origin = globalThis.location.origin

  // The QR library is loaded when the card first shows, not with the app
  const picture = shallowRef<QrPicture | null>(null)
  watch(() => props.token, async token => {
    const { qrPicture } = await import('./qrCode')
    if (token === props.token) {
      picture.value = qrPicture(scanUrl(origin, token))
    }
  }, { immediate: true })

  const confirming = ref(false)
  const busy = ref(false)
  const error = ref<string | null>(null)
  const replaced = ref(false)

  // Another station in the pane: the note belongs to the one that was replaced
  watch(() => props.station.id, () => {
    replaced.value = false
  })

  function ask (): void {
    error.value = null
    confirming.value = true
  }

  async function replace (): Promise<void> {
    busy.value = true
    error.value = null
    try {
      const updated = await qrApi.regenerate(props.station.id)
      replaced.value = true
      confirming.value = false
      emit('replaced', updated)
    } catch (error_) {
      error.value = error_ instanceof NetworkError
        ? 'This needs a connection. Nothing was changed.'
        : 'We couldn’t replace the label. Nothing was changed. Try again.'
    } finally {
      busy.value = false
    }
  }
</script>
