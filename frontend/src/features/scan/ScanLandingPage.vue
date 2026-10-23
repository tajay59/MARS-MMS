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

      <ScanCard v-else-if="state === 'offline'" :icon="mdiCloudOffOutline" title="This station is not on your phone" tone="neutral">
        Open it with a connection, or prepare a visit that includes it before you go.
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
  import { NetworkError } from '@/api/problem'
  import PageBody from '@/components/PageBody.vue'
  import { stationByToken } from '@/offline/prepared'
  import { useSessionStore } from '@/stores/session'
  import { landingStateFor, stationRoute } from './scan'
  import ScanCard from './ScanCard.vue'

  // /s/:token, the address on every label (AFD §3, §5.3; PRD QR-2 to QR-4). The router has already
  // sent a signed-out visitor to /login with this address as `next`, so the label's owner comes
  // straight back. A found station replaces this page, so Back doesn't land on it again.
  const props = defineProps<{ token: string }>()
  const router = useRouter()
  const session = useSessionStore()
  const { isStaff } = storeToRefs(session)

  const state = ref<LandingState | 'looking'>('looking')
  let abort: AbortController | null = null

  async function lookUp (): Promise<void> {
    abort?.abort()
    const mine = new AbortController()
    abort = mine
    state.value = 'looking'
    // With no connection the label is looked up among the stations prepared on this phone (QR-5)
    if ((session.offline || !navigator.onLine) && await openFromPhone(mine)) {
      return
    }
    try {
      const resolved = await qrApi.resolve(props.token, mine.signal)
      await router.replace(stationRoute(resolved))
    } catch (error) {
      if (mine.signal.aborted) {
        return
      }
      // The connection dropped on the way: the phone may still know this station
      if (error instanceof NetworkError && await openFromPhone(mine)) {
        return
      }
      state.value = landingStateFor(error)
    }
  }

  /** The prepared station this label belongs to, opened in place of this page; false when none. */
  async function openFromPhone (mine: AbortController): Promise<boolean> {
    const me = session.user
    const hit = me ? await stationByToken(me.id, props.token).catch(() => null) : null
    if (!hit || mine.signal.aborted) {
      return false
    }
    await router.replace({ name: 'stations', params: { id: hit.station.station.id } })
    return true
  }

  onMounted(lookUp)
  watch(() => props.token, lookUp)
  onBeforeUnmount(() => abort?.abort())
</script>
