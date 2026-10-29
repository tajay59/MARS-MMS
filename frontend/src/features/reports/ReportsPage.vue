<template>
  <PageBody :back="open ? { name: 'reports' } : undefined" :subtitle="subtitle" :title="chosen?.title ?? 'Reports'">
    <PaneContent pin>
      <div class="flex flex-col gap-1 px-3">
        <FeedbackBanner v-if="typesProblem" type="error">{{ typesProblem }}</FeedbackBanner>
        <v-skeleton-loader v-else-if="!types" type="list-item, list-item, list-item" />

        <template v-else>
          <section v-for="g in groups" :key="g.label" :aria-labelledby="`g-${g.label}`" class="flex flex-col gap-0.5 pb-2">
            <h3 :id="`g-${g.label}`" class="m-0 px-3 pb-1 pt-2 text-xs font-semibold text-surface-600">{{ g.label }}</h3>

            <router-link
              v-for="t in g.types"
              :key="t.type"
              :aria-current="t.type === chosen?.type ? 'true' : undefined"
              class="flex min-h-11 items-center gap-3 rounded-card px-3 py-2 text-surface-900 no-underline hover:bg-surface-100"
              :class="t.type === chosen?.type ? 'bg-primary-50 dark:bg-primary-900' : ''"
              :to="{ name: 'reports', query: { type: t.type } }"
            >
              <v-icon aria-hidden="true" class="text-surface-600" :icon="iconFor[t.type] ?? mdiFileDocumentOutline" size="20" />
              <span class="font-medium">{{ t.title }}</span>
            </router-link>
          </section>

          <p v-if="isClient" class="m-0 px-3 pt-1 text-xs text-surface-600">You can make these summaries for your own organization.</p>
        </template>
      </div>
    </PaneContent>

    <div v-if="chosen" class="flex flex-col gap-5">
      <form
        :aria-label="`${chosen.title} settings`"
        class="flex flex-col gap-4 rounded-card bg-surface-50 p-5"
        novalidate
        @submit.prevent="submit"
      >
        <div v-if="chosen.uses_period" class="grid gap-4 md:grid-cols-[repeat(2,minmax(0,1fr))_minmax(0,1.4fr)] md:items-start">
          <FormField :id="`${uid}-from`" label="From">
            <v-text-field
              :id="`${uid}-from`"
              v-model="form.from"
              density="comfortable"
              flat
              hide-details
              name="from"
              type="date"
              variant="solo-inverted"
            />
          </FormField>

          <FormField :id="`${uid}-to`" label="To">
            <v-text-field
              :id="`${uid}-to`"
              v-model="form.to"
              density="comfortable"
              flat
              hide-details
              name="to"
              type="date"
              variant="solo-inverted"
            />
          </FormField>

          <div class="flex flex-col gap-2">
            <span class="text-label text-surface-900">Quick periods</span>

            <div class="flex h-10 flex-wrap items-center gap-2">
              <button
                v-for="p in PRESETS"
                :key="p.key"
                class="inline-flex h-8 items-center rounded-full bg-surface-100 px-3 text-sm font-medium text-surface-900 hover:bg-surface-200"
                type="button"
                @click="preset(p.make)"
              >{{ p.label }}</button>
            </div>
          </div>

          <p class="m-0 text-xs text-surface-600 md:col-span-3">A month starts at 00:00 in Jamaica (America/Jamaica). Times inside the report are in that zone; a CSV file has them in UTC.</p>
        </div>

        <FormField v-if="chosen.type === 'calibration_due'" :id="`${uid}-due`" label="Look ahead (days)">
          <v-text-field
            :id="`${uid}-due`"
            v-model.number="form.dueInDays"
            density="comfortable"
            flat
            hide-details
            max="365"
            min="1"
            name="due_in_days"
            type="number"
            variant="solo-inverted"
          />
        </FormField>

        <div class="grid gap-4 md:grid-cols-3">
          <FormField v-if="!isClient" :id="`${uid}-org`" label="Organization">
            <v-select
              :id="`${uid}-org`"
              v-model="form.org"
              clearable
              density="comfortable"
              flat
              hide-details
              item-title="name"
              item-value="id"
              :items="orgs"
              placeholder="All organizations"
              variant="solo-inverted"
            />
          </FormField>

          <div v-else class="flex flex-col gap-2">
            <span class="text-label text-surface-900">Organization</span>

            <div class="flex h-10 items-center gap-2 rounded-md bg-surface-100 px-3 text-surface-700">
              <v-icon aria-hidden="true" :icon="mdiLockOutline" size="16" />{{ ownOrg }}
            </div>

            <span class="text-xs text-surface-600">Reports cover your organization only.</span>
          </div>

          <FormField v-if="!isClient" :id="`${uid}-country`" label="Country">
            <v-select
              :id="`${uid}-country`"
              v-model="form.country"
              clearable
              density="comfortable"
              flat
              hide-details
              :items="countries"
              placeholder="All countries"
              variant="solo-inverted"
            />
          </FormField>

          <FormField :id="`${uid}-stations`" label="Stations">
            <v-autocomplete
              :id="`${uid}-stations`"
              v-model="form.stations"
              chips
              clearable
              closable-chips
              density="comfortable"
              flat
              hide-details
              item-title="label"
              item-value="id"
              :items="stationItems"
              multiple
              :placeholder="isClient ? 'All our stations' : 'All stations'"
              variant="solo-inverted"
            />
          </FormField>
        </div>

        <FeedbackBanner v-if="formProblem" type="error">{{ formProblem }}</FeedbackBanner>

        <div class="flex flex-wrap items-center justify-between gap-4">
          <fieldset class="m-0 flex flex-wrap items-center gap-x-5 gap-y-1 border-0 p-0">
            <legend class="float-left mr-4 p-0 text-label text-surface-900">Format</legend>

            <v-radio-group v-model="form.format" density="compact" hide-details inline>
              <v-radio label="PDF" value="pdf" />
              <v-radio label="CSV, the table only" value="csv" />
            </v-radio-group>
          </fieldset>

          <v-btn color="primary" :loading="starting" type="submit">Generate</v-btn>
        </div>
      </form>

      <section aria-labelledby="mine-h" class="flex min-w-0 flex-col gap-2 rounded-card bg-surface-50 p-5">
        <div class="flex items-baseline justify-between gap-3">
          <h2 id="mine-h" class="m-0 text-h3 text-surface-900">Your reports</h2>
          <span class="text-xs text-surface-600">Kept for 30 days</span>
        </div>

        <FeedbackBanner v-if="jobsProblem" type="error">{{ jobsProblem }}</FeedbackBanner>
        <v-skeleton-loader v-else-if="loading" type="table-row, table-row" />
        <p v-else-if="jobs.length === 0" class="m-0 text-sm text-surface-600">Reports you make show here, newest first.</p>

        <div
          v-else
          aria-label="Your reports"
          class="overflow-x-auto"
          role="region"
          tabindex="0"
        >
          <table class="w-full border-collapse text-sm">
            <thead>
              <tr class="text-left text-xs text-surface-600">
                <th class="py-2 pr-3 font-semibold" scope="col">Report</th>
                <th class="px-3 py-2 font-semibold" scope="col">Period</th>
                <th class="px-3 py-2 font-semibold" scope="col">Format</th>
                <th class="px-3 py-2 font-semibold" scope="col">Asked</th>
                <th class="px-3 py-2 font-semibold" scope="col">Status</th>
                <th class="py-2 pl-3 text-right font-semibold" scope="col"><span class="sr-only">Action</span></th>
              </tr>
            </thead>

            <tbody>
              <tr v-for="job in jobs" :key="job.id" class="border-t border-surface-200">
                <th class="py-2.5 pr-3 text-left font-medium text-surface-900" scope="row">{{ titleOf(job.type) }}</th>
                <td class="whitespace-nowrap px-3 py-2.5 text-surface-700">{{ periodWords(job.period_from, job.period_to) }}</td>
                <td class="px-3 py-2.5 uppercase text-surface-700">{{ job.format }}</td>
                <td class="whitespace-nowrap px-3 py-2.5 text-surface-600">{{ formatListTime(job.created_at) }}</td>

                <td class="px-3 py-2.5">
                  <span class="inline-flex h-6 items-center gap-1 rounded-full pl-2 pr-2.5 text-xs font-medium" :class="chip[lookOfJob(job).state]">
                    <v-icon aria-hidden="true" :icon="iconOf[lookOfJob(job).state]" size="14" />{{ lookOfJob(job).label }}
                  </span>

                  <span v-if="job.status === 'failed'" class="mt-1 block max-w-xs text-xs text-surface-600">{{ failureWords(job.error) }}</span>
                </td>

                <td class="py-2.5 pl-3 text-right">
                  <v-btn
                    v-if="job.download_url"
                    color="primary"
                    :href="job.download_url"
                    :prepend-icon="mdiDownloadOutline"
                    rel="noopener noreferrer"
                    size="small"
                    target="_blank"
                    variant="text"
                  >Download</v-btn>

                  <v-btn v-else-if="job.status === 'failed'" size="small" variant="text" @click="setUpAgain(job)">Set up again</v-btn>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>

    <p v-else-if="types && !typesProblem" class="m-0 text-surface-600">Choose a report on the left.</p>
  </PageBody>
</template>

<script lang="ts" setup>
  import type { SummaryJob, SummaryKind, SummaryType } from '@/api/models'
  import { mdiAccountOutline, mdiAlertOutline, mdiCalendarBlankOutline, mdiCheck, mdiClockOutline, mdiDownloadOutline, mdiFileDocumentOutline, mdiHistory, mdiLockOutline, mdiProgressClock, mdiRadioTower, mdiTableLarge } from '@mdi/js'
  import { storeToRefs } from 'pinia'
  import { computed, onMounted, reactive, ref, useId, watch } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { ApiError, NetworkError } from '@/api/problem'
  import { reportsApi } from '@/api/report'
  import { formatListTime } from '@/app/format'
  import { usePaneSelection } from '@/app/shells/pane'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import FormField from '@/components/FormField.vue'
  import PageBody from '@/components/PageBody.vue'
  import PaneContent from '@/components/PaneContent.vue'
  import { useSessionStore } from '@/stores/session'
  import { useStationDirectory } from '@/stores/stationDirectory'
  import { bodyFor, emptyForm, failureWords, firstType, grouped, lookOfJob, periodWords, PRESETS, problemWith } from './summary'
  import { useSummaryJobs } from './useSummaryJobs'

  // Summary reports (PRD SUM-1 to SUM-3, CAL-4; AFD J10): pick a type, set the period and the
  // stations, ask, and download when it is ready. Staff and the Viewer make every type; a client
  // makes two, for their own organization. A report is a job on the server; this page only asks
  // and looks. It needs a connection and keeps nothing on the device (OFF-10).
  const uid = useId()
  const route = useRoute()
  const router = useRouter()
  const session = useSessionStore()
  const { user, isClient } = storeToRefs(session)
  const directory = useStationDirectory()
  const { jobs, loading, problem: jobsProblem, start } = useSummaryJobs()

  const types = ref<SummaryType[] | null>(null)
  const typesProblem = ref<string | null>(null)
  const groups = computed(() => grouped(types.value ?? []))

  const iconFor: Record<string, string> = {
    station_history: mdiHistory, network_status: mdiRadioTower, calibration_due: mdiClockOutline,
    client_activity: mdiAccountOutline, request_turnaround: mdiProgressClock,
    monthly_summary: mdiCalendarBlankOutline, annual_summary: mdiTableLarge,
  }
  const chip = {
    making: 'bg-primary-50 text-primary-800 dark:bg-primary-900 dark:text-primary-100',
    ready: 'bg-success-container text-on-success-container',
    failed: 'bg-error-container text-on-error-container',
  } as const
  const iconOf = { making: mdiProgressClock, ready: mdiCheck, failed: mdiAlertOutline } as const

  // The chosen type is in the address (?type=), so a link opens it and Back works
  const selectedKey = computed(() => typeof route.query.type === 'string' ? route.query.type : null)
  const chosen = computed(() => types.value?.find(t => t.type === selectedKey.value) ?? null)
  const open = computed(() => chosen.value !== null)
  usePaneSelection(() => open.value)

  const subtitle = computed(() => chosen.value ? `${chosen.value.description} A report is ready in about two minutes.` : undefined)
  const form = reactive(emptyForm())
  const starting = ref(false)
  const formProblem = ref<string | null>(null)

  const stationRows = computed(() => directory.stations
    .filter(s => (!form.org || s.owner_org_id === form.org) && (!form.country || s.country === form.country)))
  const stationItems = computed(() => stationRows.value.map(s => ({ id: s.id, label: `${s.code} · ${s.name}` })))
  const orgs = computed(() => [...new Map(directory.stations.map(s => [s.owner_org_id, { id: s.owner_org_id, name: s.owner_org_name ?? 'Organization' }])).values()]
    .toSorted((a, b) => a.name.localeCompare(b.name)))
  const countries = computed(() => [...new Set(directory.stations.map(s => s.country))].toSorted((a, b) => a.localeCompare(b)))
  const ownOrg = computed(() => directory.stations[0]?.owner_org_name ?? 'Your organization')

  // Narrowing the organization or country drops stations that no longer fit
  watch(() => [form.org, form.country], () => {
    const fit = new Set(stationRows.value.map(s => s.id))
    form.stations = form.stations.filter(id => fit.has(id))
  })

  function titleOf (kind: SummaryKind): string {
    return types.value?.find(t => t.type === kind)?.title ?? kind
  }

  function preset (make: (now: Date) => { from: string, to: string }): void {
    Object.assign(form, make(new Date()))
  }

  async function submit (): Promise<void> {
    const type = chosen.value
    if (!type) {
      return
    }
    formProblem.value = problemWith(form, type.uses_period)
    if (formProblem.value) {
      return
    }
    starting.value = true
    try {
      await start(bodyFor(type.type, type.uses_period, form, isClient.value))
    } catch (error) {
      formProblem.value = error instanceof NetworkError
        ? 'This needs a connection. Try again when you have signal.'
        : (error instanceof ApiError && error.status === 422
          ? error.message
          : 'We couldn’t start the report. Try again.')
    } finally {
      starting.value = false
    }
  }

  /** A failed report is set up again: its type, period and format go back in the form. */
  function setUpAgain (job: SummaryJob): void {
    Object.assign(form, { from: job.period_from ?? form.from, to: job.period_to ?? form.to, format: job.format })
    void router.replace({ query: { type: job.type } })
    formProblem.value = null
  }

  onMounted(async () => {
    try {
      types.value = await reportsApi.summaryTypes()
    } catch (error) {
      typesProblem.value = error instanceof NetworkError
        ? 'This needs a connection. It will load when you have signal.'
        : 'We couldn’t load the reports. Reload the page to try again.'
    }
    if (user.value) {
      void directory.load(user.value.id)
    }
  })

  // On a wide screen the first type is open; on a phone the list comes first
  const wide = globalThis.matchMedia?.('(min-width: 768px)').matches ?? true
  watch(types, list => {
    const first = list ? firstType(list) : null
    if (wide && first && !selectedKey.value) {
      void router.replace({ query: { type: first } })
    }
  })
</script>
