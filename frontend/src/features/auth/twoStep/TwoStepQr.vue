<template>
  <div class="flex flex-col gap-4">
    <div class="flex justify-center">
      <div class="size-44 rounded-md border border-surface-200 bg-white p-2">
        <svg
          v-if="picture"
          :aria-label="`QR code for ${issuerAccount}`"
          class="block size-full text-black"
          role="img"
          shape-rendering="crispEdges"
          :viewBox="`0 0 ${picture.size} ${picture.size}`"
        >
          <path :d="picture.path" fill="currentColor" />
        </svg>

        <v-skeleton-loader v-else class="size-full" type="image" />
      </div>
    </div>

    <div class="flex flex-col gap-1">
      <span class="text-sm text-surface-600">Can’t scan it? Enter this key in the app instead:</span>

      <div class="flex items-center gap-2">
        <code class="grow rounded-md bg-surface-100 px-3 py-2.5 font-mono text-sm tracking-wider text-surface-900 break-all">{{ groupKey(secret) }}</code>

        <v-btn
          aria-label="Copy the key"
          icon
          size="40"
          variant="outlined"
          @click="copy"
        >
          <v-icon :icon="copied ? mdiCheck : mdiContentCopy" size="20" />
        </v-btn>
      </div>

      <span aria-live="polite" class="text-xs text-surface-600">{{ copied ? 'Key copied.' : `Account: ${email} · Issuer: MARS-MMS` }}</span>
    </div>
  </div>
</template>

<script lang="ts" setup>
  import type { QrPicture } from '@/features/stations/qrCode'
  import { mdiCheck, mdiContentCopy } from '@mdi/js'
  import { onMounted, ref, watch } from 'vue'
  import { groupKey } from './twoStep'

  // The QR code and the typed key for an authenticator app (W22). The picture is drawn here from
  // the `otpauth://` address, with the lazy QR library the station labels use, so it stays out of
  // the precache (the page needs a connection anyway).
  const props = defineProps<{
    secret: string
    uri: string
    email: string
  }>()

  const picture = ref<QrPicture | null>(null)
  const copied = ref(false)
  const issuerAccount = `MARS-MMS, ${props.email}`

  async function draw (): Promise<void> {
    const { qrPicture } = await import('@/features/stations/qrCode')
    picture.value = qrPicture(props.uri)
  }

  async function copy (): Promise<void> {
    try {
      await navigator.clipboard.writeText(props.secret)
      copied.value = true
      setTimeout(() => {
        copied.value = false
      }, 3000)
    } catch {
      // No clipboard permission: the key is on screen to type
    }
  }

  onMounted(draw)
  watch(() => props.uri, draw)
</script>
