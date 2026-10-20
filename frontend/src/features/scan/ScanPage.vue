<template>
  <PageBody title="Scan a label">
    <div class="flex grow flex-col gap-3 p-3 md:mx-auto md:w-full md:max-w-xl md:p-0">
      <!-- Typing the station code -->
      <template v-if="phase === 'code'">
        <div class="flex items-center justify-between gap-3">
          <h2 class="m-0 text-h3 text-surface-900">Enter the station code</h2>

          <v-btn
            v-if="cameraPossible"
            :prepend-icon="mdiQrcodeScan"
            size="small"
            variant="tonal"
            @click="useCamera"
          >Camera</v-btn>
        </div>

        <div class="flex flex-col gap-2 rounded-card bg-surface-50 p-3.5">
          <FormField id="station-code" label="Station code">
            <v-text-field
              id="station-code"
              v-model="typed"
              autocapitalize="characters"
              autocomplete="off"
              :autofocus="finePointer"
              clearable
              enterkeyhint="go"
              hide-details
              inputmode="text"
              placeholder="JM-KIN-001"
              spellcheck="false"
              @keydown.enter.prevent="openTyped"
            >
              <template #prepend-inner><v-icon :icon="mdiKeyboardOutline" /></template>
            </v-text-field>
          </FormField>

          <p class="m-0 flex items-start gap-1.5 text-sm text-surface-600">
            <v-icon class="mt-0.5" :icon="mdiInformationOutline" size="16" />
            Printed on the QR label, under the station name.
          </p>
        </div>

        <FeedbackBanner v-if="directory.error && !directory.loaded" type="info">
          {{ online ? 'We couldn’t load the station list. Check the code on the label, or try again.' : 'The station list isn’t on this phone yet. Connect once to use the code field.' }}
        </FeedbackBanner>

        <section v-else-if="typed.trim()" aria-label="Matching stations" class="overflow-hidden rounded-card bg-surface-50">
          <div class="flex items-center justify-between gap-2 border-b border-surface-200 px-3.5 py-2.5 text-sm text-surface-600">
            <span aria-live="polite">{{ matches.length === 0 ? 'No match' : `${matches.length} ${matches.length === 1 ? 'match' : 'matches'}` }}</span>

            <span v-if="!online && directory.loaded" class="inline-flex items-center gap-1.5 font-mono text-xs font-semibold uppercase tracking-wide text-success">
              <span class="size-1.5 rounded-full bg-current" />Works offline
            </span>
          </div>

          <ul v-if="matches.length > 0" class="m-0 list-none p-0">
            <li v-for="row in matches" :key="row.id" class="relative flex h-15 items-center gap-2.5 border-t border-surface-200 px-3.5 first:border-t-0">
              <span class="min-w-0 grow">
                <span class="flex items-baseline gap-1.5">
                  <router-link
                    class="font-mono text-base font-semibold text-surface-900 no-underline after:absolute after:inset-0 focus-visible:outline-none focus-visible:after:outline-2 focus-visible:after:outline-primary"
                    :to="{ name: 'stations', params: { id: row.id } }"
                    translate="no"
                  >{{ row.code }}</router-link>

                  <span v-if="row.type" class="font-mono text-xs font-semibold uppercase tracking-wide text-surface-600">{{ row.type }}</span>
                </span>

                <span class="block truncate text-sm text-surface-600">{{ row.name }}</span>
              </span>

              <v-icon class="text-primary" :icon="mdiArrowRight" size="20" />
            </li>
          </ul>

          <p v-else class="m-0 p-3.5 text-sm text-surface-600">
            {{ directory.loading ? 'Loading the stations…' : 'No station on this phone has that code. Check it against the label.' }}
          </p>
        </section>
      </template>

      <!-- Before the browser asks: say why -->
      <ScanCard v-else-if="phase === 'asking'" :icon="mdiCameraOutline" title="Scan a station label" tone="primary">
        The camera reads the QR code on the station. Nothing is recorded or saved from the camera.
        <template #actions>
          <v-btn block color="primary" size="large" @click="useCamera">Turn on the camera</v-btn>

          <v-btn
            block
            :prepend-icon="mdiKeyboardOutline"
            size="large"
            variant="text"
            @click="phase = 'code'"
          >Enter the station code</v-btn>
        </template>
      </ScanCard>

      <!-- No camera allowed, or none to use -->
      <ScanCard
        v-else-if="phase === 'blocked'"
        :icon="mdiCameraOffOutline"
        :title="scanner.state.value === 'unavailable' ? 'The camera can’t be used' : 'The camera is turned off'"
        tone="primary"
      >
        {{ scanner.state.value === 'unavailable'
          ? 'This device has no camera the app can reach, or another app is using it. You can type the station code from the QR label.'
          : 'Allow the camera for MARS-MMS in the phone’s settings, or type the station code from the QR label.' }}
        <template #actions>
          <v-btn
            block
            color="primary"
            :prepend-icon="mdiKeyboardOutline"
            size="large"
            @click="phase = 'code'"
          >Enter the station code</v-btn>

          <v-btn
            block
            :prepend-icon="mdiRefresh"
            size="large"
            variant="text"
            @click="useCamera"
          >Try the camera again</v-btn>
        </template>
      </ScanCard>

      <!-- The camera. The picture is decoration for the eye; the status line below says what is happening. -->
      <div
        v-show="phase === 'camera'"
        class="relative grid min-h-96 grow place-items-center overflow-hidden rounded-card bg-[#0B1220] text-white md:min-h-112"
      >
        <video
          ref="video"
          aria-hidden="true"
          class="absolute inset-0 size-full object-cover"
          muted
          playsinline
        />

        <button
          v-if="scanner.torchAvailable.value"
          :aria-label="scanner.torchOn.value ? 'Turn the torch off' : 'Turn the torch on'"
          :aria-pressed="scanner.torchOn.value"
          class="absolute right-3 top-3 z-10 grid size-11 place-items-center rounded-full bg-[#0B1220]/70 text-slate-100"
          type="button"
          @click="scanner.toggleTorch()"
        >
          <v-icon :icon="scanner.torchOn.value ? mdiFlashlightOff : mdiFlashlight" />
        </button>

        <!-- The guide: four corners, green once a label is found -->
        <div aria-hidden="true" class="relative z-10 size-60 transition-colors">
          <i v-for="corner in corners" :key="corner" class="absolute size-9 border-4 border-solid" :class="[corner, found ? 'border-[#4ADE80]' : 'border-white']" />
        </div>

        <span
          v-if="found"
          class="absolute left-1/2 top-1/2 z-10 inline-flex -translate-x-1/2 -translate-y-1/2 items-center gap-2.5 rounded-full bg-white py-1.5 pl-1.5 pr-3.5 text-base font-semibold text-slate-900 shadow-lg"
        >
          <span class="grid size-7 place-items-center rounded-full bg-[#DCFCE7] text-[#15803D]"><v-icon :icon="mdiCheck" size="16" /></span>
          Label found
        </span>

        <div class="absolute inset-x-3 bottom-3.5 z-10 flex flex-col items-center gap-2.5 text-center">
          <span
            class="rounded-full px-3.5 py-2 text-sm font-medium"
            :class="found ? 'bg-[#15803D] text-white' : 'bg-[#0B1220]/80 text-slate-100'"
            role="status"
          >{{ hint }}</span>

          <button v-if="!found" class="min-h-11 px-2 text-sm font-semibold text-white underline underline-offset-4" type="button" @click="phase = 'code'">
            Enter the station code instead
          </button>
        </div>
      </div>
    </div>
  </PageBody>
</template>

<script lang="ts" setup>
  import { mdiArrowRight, mdiCameraOffOutline, mdiCameraOutline, mdiCheck, mdiFlashlight, mdiFlashlightOff, mdiInformationOutline, mdiKeyboardOutline, mdiQrcodeScan, mdiRefresh } from '@mdi/js'
  import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { useOnline } from '@/app/composables/useOnline'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import FormField from '@/components/FormField.vue'
  import PageBody from '@/components/PageBody.vue'
  import { useSessionStore } from '@/stores/session'
  import { useStationDirectory } from '@/stores/stationDirectory'
  import { suggestStations, tokenFromScan } from './scan'
  import ScanCard from './ScanCard.vue'
  import { cameraPermission, useScanner } from './useScanner'

  // /scan (AFD §3, §5.3; PRD QR-2). Staff only. The camera is asked for here and nowhere else.
  const route = useRoute()
  const router = useRouter()
  const session = useSessionStore()
  const online = useOnline()
  const directory = useStationDirectory()

  type Phase = 'asking' | 'camera' | 'blocked' | 'code'
  const phase = ref<Phase>(route.query.mode === 'code' ? 'code' : 'asking')
  const typed = ref('')
  // A keyboard that opens by itself covers the screen on a phone; the person taps the field there
  const finePointer = typeof matchMedia === 'function' && matchMedia('(pointer: fine)').matches
  const notLabel = ref(false)
  let notLabelTimer: ReturnType<typeof setTimeout> | undefined

  const cameraPossible = computed(() => typeof navigator !== 'undefined' && Boolean(navigator.mediaDevices?.getUserMedia))

  const scanner = useScanner(onFound)
  const video = scanner.video
  const found = computed(() => scanner.state.value === 'found')
  const corners = [
    'left-0 top-0 rounded-tl-2xl border-b-0 border-r-0',
    'right-0 top-0 rounded-tr-2xl border-b-0 border-l-0',
    'bottom-0 left-0 rounded-bl-2xl border-r-0 border-t-0',
    'bottom-0 right-0 rounded-br-2xl border-l-0 border-t-0',
  ]

  const hint = computed(() => {
    if (found.value) {
      return 'Opening the station…'
    }
    if (notLabel.value) {
      return 'That isn’t a MARS-MMS label. Try another.'
    }
    return scanner.state.value === 'starting' ? 'Starting the camera…' : 'Point the camera at the code on the station'
  })

  /** Whether the text is one of our labels; the scanner keeps looking when it is not. */
  function onFound (text: string): boolean {
    const token = tokenFromScan(text)
    if (token) {
      void router.push({ name: 'scan-result', params: { token } })
      return true
    }
    // Not one of ours: say so for a moment while the camera goes on looking
    notLabel.value = true
    clearTimeout(notLabelTimer)
    notLabelTimer = setTimeout(() => {
      notLabel.value = false
    }, 1800)
    return false
  }

  async function useCamera (): Promise<void> {
    phase.value = 'camera'
    await nextTick() // the video element must be on screen before the stream is attached
    await scanner.start()
  }

  watch(scanner.state, state => {
    if (phase.value === 'camera' && (state === 'denied' || state === 'unavailable')) {
      phase.value = 'blocked'
    }
  })

  // Typing a code needs the station list; it is fetched once per login and kept in memory
  watch(phase, next => {
    if (next === 'code') {
      scanner.stop()
      if (session.user) {
        void directory.load(session.user.id)
      }
    }
  }, { immediate: true })

  const matches = computed(() => suggestStations(directory.stations, typed.value))

  function openTyped (): void {
    const text = typed.value.trim()
    const exact = directory.stations.find(s => s.code.toLowerCase() === text.toLowerCase())
    const only = matches.value.length === 1 ? matches.value[0] : undefined
    const target = exact ?? only
    if (target) {
      void router.push({ name: 'stations', params: { id: target.id } })
    }
  }

  onMounted(async () => {
    if (phase.value !== 'asking') {
      return
    }
    if (!cameraPossible.value) {
      phase.value = 'blocked'
      return
    }
    // Already allowed: no need to explain again. Denied: say so at once.
    const permission = await cameraPermission()
    if (phase.value !== 'asking') {
      return
    }
    if (permission === 'granted') {
      await useCamera()
    } else if (permission === 'denied') {
      phase.value = 'blocked'
    }
  })

  onBeforeUnmount(() => clearTimeout(notLabelTimer))
</script>
