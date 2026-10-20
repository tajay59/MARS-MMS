<template>
  <PageBody title="Scan a label">
    <div class="flex grow flex-col justify-center gap-3 p-3 md:p-0 md:py-8">
      <ScanCard
        v-if="state === 'looking'"
        busy
        :icon="mdiQrcode"
        title="Opening the station"
        tone="primary"
      >
        <span role="status">This takes a moment.</span>
      </ScanCard>

      <ScanCard v-else-if="state === 'revoked'" :icon="mdiQrcode" title="This code is no longer valid" tone="warning">
        The label was replaced. Look for the newer label on the station, or find the station in the list.
        <template #actions>
          <v-btn
            block
            color="primary"
            size="large"
            :to="{ name: 'stations' }"
            variant="tonal"
          >Go to stations</v-btn>

          <v-btn
            v-if="isStaff"
            block
            :prepend-icon="mdiQrcodeScan"
            size="large"
            :to="{ name: 'scan' }"
            variant="text"
          >Scan another label</v-btn>
        </template>
      </ScanCard>

      <ScanCard v-else-if="state === 'missing'" :icon="mdiMagnify" title="We can’t find that station" tone="error">
        The code isn’t recognised. Check that you scanned a MARS-MMS label.
        <template #actions>
          <v-btn
            block
            color="primary"
            size="large"
            :to="{ name: 'dashboard' }"
            variant="tonal"
          >Go to dashboard</v-btn>

          <v-btn
            v-if="isStaff"
            block
            :prepend-icon="mdiQrcodeScan"
            size="large"
            :to="{ name: 'scan' }"
            variant="text"
          >Scan another label</v-btn>
        </template>
      </ScanCard>

      <ScanCard v-else-if="state === 'offline'" :icon="mdiCloudOffOutline" title="No signal, and this station isn’t prepared" tone="neutral">
        Stations you prepare for a visit open without signal. This one isn’t on the phone yet.
        <template #actions>
          <v-btn
            block
            color="primary"
            :prepend-icon="mdiRefresh"
            size="large"
            variant="outlined"
            @click="lookUp"
          >Try again</v-btn>

          <v-btn
            v-if="isStaff"
            block
            :prepend-icon="mdiKeyboardOutline"
            size="large"
            :to="{ name: 'scan', query: { mode: 'code' } }"
            variant="text"
          >Enter the station code</v-btn>
        </template>
      </ScanCard>

      <ScanCard v-else :icon="mdiAlertOutline" title="Something went wrong" tone="error">
        We couldn’t open the station. Try again in a moment.
        <template #actions>
          <v-btn
            block
            color="primary"
            :prepend-icon="mdiRefresh"
            size="large"
            variant="outlined"
            @click="lookUp"
          >Try again</v-btn>
        </template>
      </ScanCard>
    </div>
  </PageBody>
</template>

<script lang="ts" setup>
  import type { LandingState } from './scan'
  import { mdiAlertOutline, mdiCloudOffOutline, mdiKeyboardOutline, mdiMagnify, mdiQrcode, mdiQrcodeScan, mdiRefresh } from '@mdi/js'
  import { storeToRefs } from 'pinia'
  import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
  import { useRouter } from 'vue-router'
  import { qrApi } from '@/api/operations'
  import PageBody from '@/components/PageBody.vue'
  import { useSessionStore } from '@/stores/session'
  import { landingStateFor, stationRoute } from './scan'
  import ScanCard from './ScanCard.vue'

  // /s/:token, the address on every label (AFD §3, §5.3; PRD QR-2 to QR-4). The router has already
  // sent a signed-out visitor to /login with this address as `next`, so the label's owner comes
  // straight back. A found station replaces this page, so Back doesn't land on it again.
  const props = defineProps<{ token: string }>()
  const router = useRouter()
  const { isStaff } = storeToRefs(useSessionStore())

  const state = ref<LandingState | 'looking'>('looking')
  let abort: AbortController | null = null

  async function lookUp (): Promise<void> {
    abort?.abort()
    const mine = new AbortController()
    abort = mine
    state.value = 'looking'
    try {
      const resolved = await qrApi.resolve(props.token, mine.signal)
      await router.replace(stationRoute(resolved))
    } catch (error) {
      if (mine.signal.aborted) {
        return
      }
      state.value = landingStateFor(error)
    }
  }

  onMounted(lookUp)
  watch(() => props.token, lookUp)
  onBeforeUnmount(() => abort?.abort())
</script>
