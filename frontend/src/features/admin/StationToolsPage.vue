<template>
  <PageBody subtitle="Print a sheet of labels to stick on stations." title="QR labels">
    <div class="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,264px)]">
      <!-- Which stations -->
      <div class="flex min-w-0 flex-col gap-4">
        <FeedbackBanner v-if="!online" type="warning">
          <strong>This needs a connection.</strong> Your selection is kept until you have signal.
        </FeedbackBanner>

        <FeedbackBanner v-if="loadError" type="error">{{ loadError }}</FeedbackBanner>

        <template v-else>
          <div class="grid gap-3 sm:grid-cols-2">
            <v-text-field
              v-model="search"
              aria-label="Search stations by code or name"
              autocomplete="off"
              clearable
              hide-details
              placeholder="Search code or name"
              :prepend-inner-icon="mdiMagnify"
              spellcheck="false"
              type="search"
            />

            <v-select
              v-model="country"
              aria-label="Country"
              clearable
              hide-details
              :items="countryItems"
              placeholder="All countries"
            />
          </div>

          <div v-if="directory.loading && !directory.loaded" aria-label="Loading stations…" role="status">
            <v-skeleton-loader v-for="n in 4" :key="n" type="list-item" />
          </div>

          <p v-else-if="rows.length === 0" class="m-0 py-6 text-center text-surface-600">
            {{ directory.stations.length === 0 ? 'No stations yet. They arrive with the station import.' : 'No stations match.' }}
          </p>

          <div v-else class="overflow-hidden rounded-card bg-surface-50">
            <div class="grid grid-cols-[28px_minmax(0,120px)_minmax(0,1fr)] items-center gap-2 bg-surface-100 px-3 py-2 text-xs font-medium text-surface-700 sm:grid-cols-[28px_minmax(0,120px)_minmax(0,1fr)_minmax(0,140px)]">
              <v-checkbox-btn
                aria-label="Select every station shown"
                density="compact"
                :indeterminate="someShown && !allShown"
                :model-value="allShown"
                @update:model-value="toggleShown"
              />

              <span>Code</span>
              <span>Name</span>
              <span class="hidden sm:inline">Organization</span>
            </div>

            <ul class="m-0 max-h-96 list-none overflow-y-auto p-0">
              <li v-for="row in rows" :key="row.id" class="border-t border-surface-200">
                <label class="grid min-h-11 cursor-pointer grid-cols-[28px_minmax(0,120px)_minmax(0,1fr)] items-center gap-2 px-3 text-sm hover:bg-surface-50 sm:grid-cols-[28px_minmax(0,120px)_minmax(0,1fr)_minmax(0,140px)]">
                  <v-checkbox-btn
                    density="compact"
                    :model-value="chosen.has(row.id)"
                    @update:model-value="toggle(row.id, Boolean($event))"
                  />

                  <span class="truncate font-mono font-medium text-surface-900" translate="no">{{ row.code }}</span>
                  <span class="truncate text-surface-900">{{ row.name }}</span>
                  <span class="hidden truncate text-surface-600 sm:inline">{{ row.owner_org_name }}</span>
                </label>
              </li>
            </ul>
          </div>

          <div class="flex flex-wrap items-center justify-between gap-2">
            <span aria-live="polite" class="text-sm text-surface-600">{{ chosen.size }} selected of {{ rows.length }} shown</span>

            <span class="flex gap-1">
              <v-btn class="text-primary" size="small" variant="text" @click="selectShown">Select all {{ rows.length }}</v-btn>
              <v-btn class="text-primary" size="small" variant="text" @click="chosen = new Set()">Clear</v-btn>
            </span>
          </div>

          <FormField id="label-phone" label="Contact phone (optional)">
            <v-text-field
              id="label-phone"
              v-model="phone"
              autocomplete="off"
              :error-messages="phoneError ?? undefined"
              inputmode="tel"
              placeholder="+1 876 555 0100"
            />

            <p class="m-0 text-sm text-surface-600">Printed on every label, for whoever finds the station. Leave empty to print none.</p>
          </FormField>
        </template>
      </div>

      <!-- The sheet -->
      <div class="flex min-w-0 flex-col gap-3">
        <h2 class="m-0 text-xs font-medium uppercase tracking-wide text-surface-600">Sheet preview</h2>

        <div
          :aria-label="`Preview of the A4 sheet: ${preview.length} of ${PER_PAGE} labels on the first page`"
          class="mx-auto grid aspect-[210/297] w-full max-w-72 grid-cols-2 grid-rows-5 bg-white px-[3.3%] py-[5.2%] text-black shadow-md"
          role="img"
        >
          <div
            v-for="n in PER_PAGE"
            :key="n"
            class="flex min-w-0 items-center gap-[6%] border border-dashed p-[4%]"
            :class="preview[n - 1] ? 'border-slate-400' : 'border-dotted border-slate-300 opacity-40'"
          >
            <template v-if="preview[n - 1]">
              <v-icon class="shrink-0 text-black" :icon="mdiQrcode" size="38" />

              <span class="min-w-0">
                <b class="block text-[6px] leading-tight">MARS-MMS</b>
                <b class="block truncate text-[8px] leading-tight">{{ preview[n - 1]?.name }}</b>
                <span class="mt-0.5 block truncate font-mono text-[6px] font-medium">{{ preview[n - 1]?.code }}</span>
              </span>
            </template>
          </div>
        </div>

        <p class="m-0 text-center text-sm text-surface-600">{{ chosen.size === 0 ? 'Choose stations to see the sheet.' : sheetNote(chosen.size) }}</p>

        <v-btn
          block
          color="primary"
          :disabled="chosen.size === 0 || running || !online || phoneError !== null"
          :loading="running"
          :prepend-icon="mdiPrinterOutline"
          size="large"
          @click="make"
        >Make label sheet</v-btn>

        <p v-if="chosen.size > MAX_STATIONS" class="m-0 text-sm text-error" role="alert">
          A sheet holds up to {{ MAX_STATIONS }} labels. Make one sheet for each group.
        </p>
      </div>
    </div>

    <!-- The job -->
    <div aria-live="polite" class="mt-6 flex flex-col gap-3">
      <div v-if="running" class="flex items-center gap-3 rounded-card bg-surface-100 px-3.5 py-3" role="status">
        <v-progress-circular color="primary" indeterminate size="28" width="3" />

        <span>
          <strong class="block text-surface-900">Making your label sheet</strong>
          <span class="text-sm text-surface-600">{{ runningNote }} Usually a few seconds.</span>
        </span>
      </div>

      <template v-else-if="job?.status === 'done' && job.result">
        <div class="flex flex-wrap items-center gap-3 rounded-card bg-primary-50 px-3.5 py-3">
          <v-icon class="text-primary" :icon="mdiFilePdfBox" size="28" />

          <span class="min-w-0 grow">
            <strong class="block text-surface-900">Station labels · {{ pagesText }} · {{ labelsText }}</strong>
            <span class="text-sm text-surface-600">The link works for 10 minutes. Make a new sheet after that.</span>
          </span>

          <v-btn
            v-if="job.result.download_url"
            color="primary"
            :href="job.result.download_url"
            rel="noopener"
            target="_blank"
          >Open PDF</v-btn>
        </div>

        <FeedbackBanner v-if="job.result.missing.length > 0" type="warning">
          {{ job.result.missing.length }} {{ job.result.missing.length === 1 ? 'station was' : 'stations were' }} left out because
          {{ job.result.missing.length === 1 ? 'it no longer exists' : 'they no longer exist' }}.
        </FeedbackBanner>
      </template>

      <template v-else-if="failure">
        <FeedbackBanner type="error"><strong>The sheet couldn’t be made.</strong> {{ failure }}</FeedbackBanner>
        <div><v-btn color="primary" variant="outlined" @click="make">Try again</v-btn></div>
      </template>
    </div>
  </PageBody>
</template>

<script lang="ts" setup>
  import type { JobOut } from '@/api/models'
  import { mdiFilePdfBox, mdiMagnify, mdiPrinterOutline, mdiQrcode } from '@mdi/js'
  import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
  import { useRoute } from 'vue-router'
  import { ApiError, NetworkError } from '@/api/problem'
  import { reportsApi } from '@/api/report'
  import { useOnline } from '@/app/composables/useOnline'
  import { countryName } from '@/app/countries'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import FormField from '@/components/FormField.vue'
  import PageBody from '@/components/PageBody.vue'
  import { useSessionStore } from '@/stores/session'
  import { useStationDirectory } from '@/stores/stationDirectory'
  import { MAX_STATIONS, PER_PAGE, phoneProblem, pickable, PollGaveUp, pollJob, sheetNote } from './labels'

  // /admin/stations-tools (AFD §3; PRD QR-6). Admin only: the report service refuses everyone
  // else, and the router shows them the Not found page. The sheet is drawn on the server.
  const JOB_KEY = 'mms.labels.job'
  const route = useRoute()
  const session = useSessionStore()
  const online = useOnline()
  const directory = useStationDirectory()

  const search = ref('')
  const country = ref<string | null>(null)
  const phone = ref('')
  const chosen = ref<Set<string>>(new Set())

  const job = ref<JobOut | null>(null)
  const running = ref(false)
  const failure = ref<string | null>(null)
  const stationCountAtStart = ref(0)
  let abort: AbortController | null = null

  // --- Choosing -----------------------------------------------------------------------------------

  const rows = computed(() => pickable(directory.stations, search.value, country.value))
  const allShown = computed(() => rows.value.length > 0 && rows.value.every(r => chosen.value.has(r.id)))
  const someShown = computed(() => rows.value.some(r => chosen.value.has(r.id)))
  const countryItems = computed(() =>
    [...new Set(directory.stations.map(s => s.country))]
      .map(code => ({ value: code, title: countryName(code) }))
      .toSorted((a, b) => a.title.localeCompare(b.title)),
  )
  const phoneError = computed(() => phoneProblem(phone.value))
  const loadError = computed(() => {
    if (!directory.error || directory.loaded) {
      return null
    }
    return directory.error instanceof NetworkError
      ? 'This needs a connection. The stations will load when you have signal.'
      : 'We couldn’t load the stations. Reload the page to try again.'
  })

  /** The first labels of the sheet, in the order the sheet will print them (by code). */
  const preview = computed(() =>
    directory.stations.filter(s => chosen.value.has(s.id)).slice(0, PER_PAGE),
  )

  function toggle (id: string, on: boolean): void {
    const next = new Set(chosen.value)
    if (on) {
      next.add(id)
    } else {
      next.delete(id)
    }
    chosen.value = next
  }

  function toggleShown (on: boolean | null): void {
    const next = new Set(chosen.value)
    for (const row of rows.value) {
      if (on) {
        next.add(row.id)
      } else {
        next.delete(row.id)
      }
    }
    chosen.value = next
  }

  function selectShown (): void {
    toggleShown(true)
  }

  // --- Making the sheet ----------------------------------------------------------------------------

  const pagesText = computed(() => {
    const pages = job.value?.result?.pages ?? 0
    return `${pages} ${pages === 1 ? 'page' : 'pages'}`
  })
  const labelsText = computed(() => {
    const count = job.value?.result?.stations ?? 0
    return `${count} ${count === 1 ? 'label' : 'labels'}`
  })
  const runningNote = computed(() => {
    const n = stationCountAtStart.value
    return n > 0 ? `${n} ${n === 1 ? 'station' : 'stations'}.` : ''
  })

  function remember (id: string | null): void {
    try {
      if (id) {
        sessionStorage.setItem(JOB_KEY, id)
      } else {
        sessionStorage.removeItem(JOB_KEY)
      }
    } catch {
      // Storage can be blocked; the sheet then just isn't offered again after leaving the page
    }
  }

  function message (error: unknown): string {
    if (error instanceof NetworkError) {
      return 'There is no connection. Nothing was printed. Try again when you have signal.'
    }
    if (error instanceof ApiError && error.status === 422) {
      return error.fieldErrors().contact_phone ?? 'Check the stations and the phone number.'
    }
    if (error instanceof PollGaveUp) {
      return 'It is taking longer than usual. Nothing was printed. Try again in a minute.'
    }
    return 'The label service didn’t answer. Nothing was printed. Try again in a minute.'
  }

  async function finish (id: string): Promise<void> {
    abort?.abort()
    const mine = new AbortController()
    abort = mine
    running.value = true
    try {
      const done = await pollJob(reportsApi.job, id, { signal: mine.signal })
      job.value = done
      if (done.status === 'failed') {
        failure.value = 'The label service couldn’t draw the sheet. Nothing was printed. Try again in a minute.'
        remember(null)
      } else {
        remember(id)
      }
    } catch (error) {
      if (!mine.signal.aborted) {
        failure.value = message(error)
        remember(null)
      }
    } finally {
      if (abort === mine) {
        running.value = false
      }
    }
  }

  async function make (): Promise<void> {
    if (running.value || chosen.value.size === 0) {
      return
    }
    failure.value = null
    job.value = null
    stationCountAtStart.value = chosen.value.size
    // In the order the sheet prints: by code
    const ids = directory.stations.filter(s => chosen.value.has(s.id)).map(s => s.id)
    running.value = true
    try {
      const started = await reportsApi.startLabels({ station_ids: ids, contact_phone: phone.value.trim() || undefined })
      await finish(started.id)
    } catch (error) {
      failure.value = message(error)
      running.value = false
    }
  }

  // --- Start ----------------------------------------------------------------------------------------

  onMounted(async () => {
    if (session.user) {
      await directory.load(session.user.id)
    }
    // "Print this label" on a station's page arrives with ?station=<id>
    const wanted = route.query.station
    const id = Array.isArray(wanted) ? wanted[0] : wanted
    if (typeof id === 'string' && directory.stations.some(s => s.id === id)) {
      chosen.value = new Set([id])
    }
    // A sheet made before the person left the page is still theirs to open
    let earlier: string | null = null
    try {
      earlier = sessionStorage.getItem(JOB_KEY)
    } catch {
      earlier = null
    }
    if (earlier && !running.value) {
      try {
        const found = await reportsApi.job(earlier)
        if (found.status === 'done' || found.status === 'failed') {
          job.value = found.status === 'done' ? found : null
          if (found.status === 'failed') {
            remember(null)
          }
        } else {
          await finish(earlier)
        }
      } catch {
        remember(null) // gone or not theirs: nothing to offer
      }
    }
  })

  // A new selection makes an old sheet stale: it no longer matches what is chosen
  watch(chosen, () => {
    if (!running.value && job.value) {
      job.value = null
      remember(null)
    }
  })

  onBeforeUnmount(() => abort?.abort())
</script>
