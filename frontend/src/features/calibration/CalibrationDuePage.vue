<template>
  <PageBody :subtitle="summary" title="Calibration due" wide>
    <!-- Phones: the filters open in a sheet, from a button in the header -->
    <template v-if="!mdAndUp" #actions>
      <v-btn :prepend-icon="mdiFilterVariant" variant="tonal" @click="sheet = true">
        Filters<span v-if="activeCount" class="ml-1 tabular-nums"><span class="sr-only">, </span>{{ activeCount }}<span class="sr-only"> active</span></span>
      </v-btn>
    </template>

    <!-- The pane: how far ahead, and whose. Phones pin it with the header, and the counts are in the header's summary there. -->
    <PaneContent pin>
      <div class="flex flex-col gap-4 px-4">
        <!-- An accordion: open on wide screens, closed on phones, where its summary says what is set -->
        <h2 v-if="mdAndUp" class="m-0 text-sm font-semibold text-surface-900">
          <button
            :aria-controls="panelId"
            :aria-expanded="showOpen"
            class="-mx-2 flex w-[calc(100%+16px)] items-center gap-2 rounded-lg px-2 py-1.5 text-left hover:bg-surface-100"
            type="button"
            @click="showOpen = !showOpen"
          >
            <span class="grow">Show<span v-if="!showOpen" class="ml-2 font-normal text-surface-600">{{ showSummary }}</span></span>
            <v-icon class="text-surface-600 transition-transform duration-200" :class="showOpen ? 'rotate-180' : ''" :icon="mdiChevronDown" size="20" />
          </button>
        </h2>

        <v-expand-transition v-if="mdAndUp">
          <DueFilterFields
            v-show="showOpen"
            :id="panelId"
            :countries="countryItems"
            :filters="filters"
            :orgs="orgs"
            :windows="windows"
            @change="setFilters"
          />
        </v-expand-transition>

        <dl class="m-0 flex flex-wrap items-center gap-x-5 gap-y-1 border-t border-surface-200 pt-3 text-sm max-md:hidden">
          <div class="flex items-center gap-2">
            <dt class="inline-flex items-center gap-2 text-surface-700"><span class="size-2.5 rounded-full bg-error" />Overdue</dt>
            <dd class="m-0 font-semibold tabular-nums text-surface-900">{{ counts.overdue }}</dd>
          </div>

          <div class="flex items-center gap-2">
            <dt class="inline-flex items-center gap-2 text-surface-700"><span class="size-2.5 rounded-full bg-warning" />Due in {{ filters.within }} days</dt>
            <dd class="m-0 font-semibold tabular-nums text-surface-900">{{ counts.soon }}</dd>
          </div>
        </dl>
      </div>
    </PaneContent>

    <FeedbackBanner v-if="error" type="error">{{ error }}</FeedbackBanner>

    <div v-else-if="all === null" aria-label="Loading calibrations due…" class="flex flex-col gap-2" role="status">
      <v-skeleton-loader v-for="n in 4" :key="n" type="list-item-two-line" />
    </div>

    <p v-else-if="shown.length === 0" class="m-0 py-10 text-center text-surface-600">
      Nothing is overdue or due in the next {{ filters.within }} days{{ filtered ? ' for these filters' : '' }}.
    </p>

    <template v-else>
      <!-- From 768 px: a table -->
      <div v-if="mdAndUp" class="overflow-x-auto">
        <table class="w-full border-collapse text-sm">
          <caption class="sr-only">Sensors overdue or due for calibration</caption>

          <thead>
            <tr class="bg-surface-100 text-left">
              <th v-for="h in ['Station', 'Sensor', 'Serial', 'Last calibrated', 'Calibration']" :key="h" class="whitespace-nowrap px-4 py-3 text-xs font-medium text-surface-700" scope="col">{{ h }}</th>
            </tr>
          </thead>

          <tbody>
            <tr v-for="u in shown" :key="u.unit_id" class="h-16 border-t border-surface-200 hover:bg-surface-50">
              <td class="px-4 py-2">
                <router-link
                  v-if="u.station"
                  class="font-medium text-surface-900 no-underline hover:text-primary"
                  :to="{ name: 'stations', params: { id: u.station.id }, query: { tab: 'sensors' } }"
                >{{ u.station.name }}</router-link>

                <span v-else class="text-surface-600">Not installed</span>

                <div v-if="u.station" class="text-xs text-surface-600"><span class="font-mono" translate="no">{{ u.station.code }}</span> · {{ countryName(u.station.country) }}</div>
              </td>

              <td class="px-4 text-surface-900"><span v-if="u.parameter" class="font-mono" translate="no">{{ u.parameter }}</span><span v-else>{{ kindLabel(u.model.kind) }}</span> · {{ u.model.manufacturer }} {{ u.model.model }}</td>
              <td class="whitespace-nowrap px-4 font-mono text-surface-900" translate="no">{{ u.serial }}</td>
              <td class="whitespace-nowrap px-4 tabular-nums" :class="u.last_calibrated_at ? 'text-surface-900' : 'text-surface-600'">{{ u.last_calibrated_at ? formatDate(u.last_calibrated_at) : 'Not calibrated' }}</td>

              <td class="px-4">
                <span class="inline-flex h-6 items-center gap-1 whitespace-nowrap rounded-full px-2.5 text-xs font-medium" :class="dueLook[stateOf(u)]">
                  <v-icon v-if="stateOf(u) === 'overdue'" class="-ml-0.5" :icon="mdiCalendarAlertOutline" size="14" />{{ dueText(u.calibration_due_at, now) }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <ul v-else aria-label="Sensors overdue or due for calibration" class="m-0 flex list-none flex-col gap-1 p-0">
        <li v-for="u in shown" :key="u.unit_id" class="relative flex items-center gap-4 rounded-3xl px-3 py-3 active:bg-surface-100">
          <span class="grid size-14 shrink-0 place-items-center rounded-full" :class="dueLook[stateOf(u)]">
            <v-icon :icon="stateOf(u) === 'overdue' ? mdiCalendarAlertOutline : mdiCalendarClockOutline" size="28" />
          </span>

          <span class="flex min-w-0 grow flex-col gap-0.5">
            <span class="truncate text-base font-medium text-surface-900">
              <span v-if="u.parameter" class="font-mono" translate="no">{{ u.parameter }}</span><span v-else>{{ kindLabel(u.model.kind) }}</span> · {{ u.model.manufacturer }} {{ u.model.model }}
            </span>

            <span class="truncate text-sm text-surface-600">
              <router-link
                v-if="u.station"
                class="text-surface-900 no-underline after:absolute after:inset-0 after:rounded-3xl"
                :to="{ name: 'stations', params: { id: u.station.id }, query: { tab: 'sensors' } }"
              >{{ u.station.name }}</router-link>

              · <span class="font-mono" translate="no">{{ u.serial }}</span>
            </span>

            <span class="mt-1 inline-flex h-6 w-fit items-center whitespace-nowrap rounded-full px-2.5 text-xs font-medium" :class="dueLook[stateOf(u)]">{{ dueText(u.calibration_due_at, now) }}</span>
          </span>
        </li>
      </ul>

      <p class="m-0 mt-4 text-sm text-surface-600">Select a station to open its Sensors tab. Recording a calibration, with its certificate, is on the station’s Calibration tab.</p>
    </template>

    <!-- Phones: the filters -->
    <v-bottom-sheet v-model="sheet" aria-labelledby="due-filters-h">
      <div class="flex flex-col gap-5 rounded-t-card bg-surface px-5 pb-[calc(20px+env(safe-area-inset-bottom))] pt-5">
        <div class="flex items-center justify-between">
          <h2 id="due-filters-h" class="m-0 text-h2 text-surface-900">Filters</h2>
          <v-btn class="text-primary" variant="text" @click="reset">Reset</v-btn>
        </div>

        <DueFilterFields
          :countries="countryItems"
          :filters="filters"
          :orgs="orgs"
          :windows="windows"
          @change="setFilters"
        />

        <v-btn block color="primary" @click="sheet = false">Show {{ shown.length }} {{ shown.length === 1 ? 'sensor' : 'sensors' }}</v-btn>
      </div>
    </v-bottom-sheet>
  </PageBody>
</template>

<script lang="ts" setup>
  import type { DueFilters } from './calibration'
  import type { DueUnit } from '@/api/models'
  import type { DueState } from '@/features/stations/stations'
  import { mdiCalendarAlertOutline, mdiCalendarClockOutline, mdiChevronDown, mdiFilterVariant } from '@mdi/js'
  import { computed, ref, useId, watch } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { useDisplay } from 'vuetify'
  import { calibrationsApi } from '@/api/operations'
  import { NetworkError } from '@/api/problem'
  import { countryName } from '@/app/countries'
  import { formatDate } from '@/app/format'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import PageBody from '@/components/PageBody.vue'
  import PaneContent from '@/components/PaneContent.vue'
  import { dueLook, kindLabel } from '@/features/stations/stations'
  import { countDue, dueFiltersFrom, dueQueryFrom, dueText, matchesDue, sortDue, WINDOWS } from './calibration'
  import DueFilterFields from './DueFilterFields.vue'

  // /calibration (AFD §3; PRD CAL-4): every installed sensor overdue or due within the window,
  // overdue first. Staff only. The window is the server's; the organization and country filters
  // narrow what came back, so the options always match what is on the list.
  const route = useRoute()
  const router = useRouter()
  const { mdAndUp } = useDisplay()

  const all = ref<DueUnit[] | null>(null)
  const error = ref<string | null>(null)
  const now = new Date()

  const filters = computed(() => dueFiltersFrom(route.query))
  const windows = WINDOWS.map(days => ({ value: days, title: `${days} days` }))
  const shown = computed(() => sortDue((all.value ?? []).filter(u => matchesDue(u, filters.value))))
  const counts = computed(() => countDue(shown.value, now))
  // The filters' accordion
  const panelId = useId()
  const showOpen = ref(mdAndUp.value)
  const showSummary = computed(() => {
    const set = (filters.value.org === null ? 0 : 1) + (filters.value.country === null ? 0 : 1)
    return `${filters.value.within} days${set > 0 ? ` · ${set} ${set === 1 ? 'filter' : 'filters'}` : ''}`
  })
  const sheet = ref(false)
  const activeCount = computed(() => (filters.value.org === null ? 0 : 1) + (filters.value.country === null ? 0 : 1) + (filters.value.within === 30 ? 0 : 1))
  const filtered = computed(() => filters.value.org !== null || filters.value.country !== null)

  const orgs = computed(() => {
    const found = new Map<string, string>()
    for (const u of all.value ?? []) {
      if (u.station) {
        found.set(u.station.owner_org_id, u.station.owner_org_name ?? u.station.owner_org_id)
      }
    }
    return [...found].map(([value, title]) => ({ value, title })).toSorted((a, b) => a.title.localeCompare(b.title))
  })
  const countryItems = computed(() => [...new Set((all.value ?? []).flatMap(u => u.station ? [u.station.country] : []))]
    .map(value => ({ value, title: countryName(value) }))
    .toSorted((a, b) => a.title.localeCompare(b.title)))

  const summary = computed(() => {
    if (!all.value || error.value) {
      return undefined
    }
    const n = shown.value.length
    if (n === 0) {
      return undefined
    }
    return `${n} ${n === 1 ? 'sensor' : 'sensors'}: ${counts.value.overdue} overdue and ${counts.value.soon} due in the next ${filters.value.within} days. Overdue first.`
  })

  function stateOf (unit: DueUnit): DueState {
    return new Date(unit.calibration_due_at).getTime() < now.getTime() ? 'overdue' : 'due_soon'
  }

  function setFilters (patch: Partial<DueFilters>): void {
    void router.replace({ query: dueQueryFrom({ ...filters.value, ...patch }) })
  }

  function reset (): void {
    void router.replace({ query: {} })
  }

  async function load (): Promise<void> {
    all.value = null
    error.value = null
    const within = filters.value.within
    try {
      const result = await calibrationsApi.due(within)
      if (within === filters.value.within) {
        all.value = result.items
      }
    } catch (error_) {
      error.value = error_ instanceof NetworkError
        ? 'This needs a connection. It will load when you have signal.'
        : 'We couldn’t load the list. Reload the page to try again.'
    }
  }

  // Only the window needs the server; the other filters work on what came back
  watch(() => filters.value.within, load, { immediate: true })
</script>
