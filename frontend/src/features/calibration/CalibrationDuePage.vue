<template>
  <PageBody :subtitle="summary" title="Calibration due" wide>
    <!-- The pane: how far ahead, and whose -->
    <PaneContent>
      <div class="flex flex-col gap-4 px-4">
        <h2 class="m-0 text-sm font-semibold text-surface-900">Show</h2>

        <FormField id="due-within" label="Due within">
          <v-select
            id="due-within"
            item-title="title"
            item-value="value"
            :items="windows"
            :model-value="filters.within"
            @update:model-value="setFilters({ within: $event })"
          />
        </FormField>

        <FormField id="due-org" label="Organization">
          <v-select
            id="due-org"
            clearable
            item-title="title"
            item-value="value"
            :items="orgs"
            :model-value="filters.org"
            placeholder="All organizations"
            @update:model-value="setFilters({ org: $event ?? null })"
          />
        </FormField>

        <FormField id="due-country" label="Country">
          <v-select
            id="due-country"
            clearable
            item-title="title"
            item-value="value"
            :items="countryItems"
            :model-value="filters.country"
            placeholder="All countries"
            @update:model-value="setFilters({ country: $event ?? null })"
          />
        </FormField>

        <dl class="m-0 flex flex-col gap-1 border-t border-surface-200 pt-3 text-sm">
          <div class="flex items-center justify-between">
            <dt class="inline-flex items-center gap-2 text-surface-700"><span class="size-2.5 rounded-full bg-error" />Overdue</dt>
            <dd class="m-0 font-semibold tabular-nums text-surface-900">{{ counts.overdue }}</dd>
          </div>

          <div class="flex items-center justify-between">
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

      <ul v-else aria-label="Sensors overdue or due for calibration" class="m-0 flex list-none flex-col p-0">
        <li v-for="u in shown" :key="u.unit_id" class="relative flex flex-col gap-1 border-t border-surface-200 py-3 first:border-t-0">
          <span class="flex items-start justify-between gap-2">
            <span class="font-medium text-surface-900">
              <span v-if="u.parameter" class="font-mono" translate="no">{{ u.parameter }}</span><span v-else>{{ kindLabel(u.model.kind) }}</span> · {{ u.model.manufacturer }} {{ u.model.model }}
            </span>

            <span class="inline-flex h-6 shrink-0 items-center whitespace-nowrap rounded-full px-2.5 text-xs font-medium" :class="dueLook[stateOf(u)]">{{ dueText(u.calibration_due_at, now) }}</span>
          </span>

          <span class="text-sm text-surface-600">
            <router-link
              v-if="u.station"
              class="text-surface-900 no-underline after:absolute after:inset-0"
              :to="{ name: 'stations', params: { id: u.station.id }, query: { tab: 'sensors' } }"
            >{{ u.station.name }}</router-link>

            · <span class="font-mono" translate="no">{{ u.serial }}</span>
          </span>
        </li>
      </ul>

      <p class="m-0 mt-4 text-sm text-surface-600">Select a station to open its Sensors tab. Recording a calibration, with its certificate, is on the station’s Calibration tab.</p>
    </template>
  </PageBody>
</template>

<script lang="ts" setup>
  import type { DueFilters } from './calibration'
  import type { DueUnit } from '@/api/models'
  import type { DueState } from '@/features/stations/stations'
  import { mdiCalendarAlertOutline } from '@mdi/js'
  import { computed, ref, watch } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { useDisplay } from 'vuetify'
  import { calibrationsApi } from '@/api/operations'
  import { NetworkError } from '@/api/problem'
  import { countryName } from '@/app/countries'
  import { formatDate } from '@/app/format'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import FormField from '@/components/FormField.vue'
  import PageBody from '@/components/PageBody.vue'
  import PaneContent from '@/components/PaneContent.vue'
  import { dueLook, kindLabel } from '@/features/stations/stations'
  import { countDue, dueFiltersFrom, dueQueryFrom, dueText, matchesDue, sortDue, WINDOWS } from './calibration'

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
