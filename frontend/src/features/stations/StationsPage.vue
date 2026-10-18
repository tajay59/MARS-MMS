<template>
  <PageBody
    :back="routeId ? { name: 'stations', query: listQuery } : undefined"
    back-label="Back to stations"
    :record="routeId"
    :subtitle="routeId ? undefined : summary"
    :title="routeId ? (detail?.name ?? 'Station') : undefined"
    :wide="!routeId"
  >
    <template v-if="detail" #subtitle>
      <span class="font-mono font-medium text-surface-900">{{ detail.code }}</span>
      <StationStatusChip :status="detail.status" />
      <span :title="detail.time_zone">{{ countryName(detail.country) }} · {{ zoneAbbreviation(detail.time_zone) }}</span>
      <span v-if="isStaff && detail.owner_org_name">· {{ detail.owner_org_name }}</span>
    </template>

    <template v-if="!routeId && isClient" #actions>
      <v-btn color="primary" :to="{ name: 'request-new' }">Report a problem</v-btn>
    </template>

    <template v-else-if="detail && isClient" #actions>
      <v-btn color="primary" :to="{ name: 'request-new', query: { station: detail.id } }">Report a problem</v-btn>
    </template>

    <!-- The pane: search and filters for the list; with a station open, the stations to switch to -->
    <PaneContent>
      <div class="flex flex-col gap-4 px-3">
        <v-text-field
          aria-label="Search stations by code or name"
          autocomplete="off"
          class="px-1"
          clearable
          hide-details
          :model-value="filters.q"
          placeholder="Search code or name"
          :prepend-inner-icon="mdiMagnify"
          spellcheck="false"
          type="search"
          @update:model-value="setFilters({ q: $event ?? '' })"
        />

        <!-- Phones: status as a row of chips, the rest in a sheet -->
        <div v-if="!routeId && !mdAndUp" aria-label="Filter by status" class="-mx-3 flex gap-1.5 overflow-x-auto px-4 pb-1" role="group">
          <button
            v-for="option in statusOptions"
            :key="option.value ?? 'all'"
            :aria-pressed="filters.status === option.value"
            class="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-full border px-3 text-sm font-medium"
            :class="filters.status === option.value ? 'border-transparent bg-primary-100 text-primary-700 dark:bg-primary-800 dark:text-primary-100' : 'border-surface-300 text-surface-900'"
            type="button"
            @click="setFilters({ status: option.value })"
          >
            <StationStatusMark v-if="option.value" :status="option.value" />
            {{ option.label }}<span class="tabular-nums text-surface-600">{{ option.count }}</span>
          </button>

          <button
            class="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-full border border-surface-300 px-3 text-sm font-medium text-surface-900"
            type="button"
            @click="sheet = true"
          >
            <v-icon :icon="mdiFilterVariant" size="16" />
            More filters<span v-if="extraFilters" class="tabular-nums text-primary">{{ extraFilters }}</span>
          </button>
        </div>

        <!-- From 768 px: the full set of filters -->
        <template v-else-if="!routeId">
          <div aria-labelledby="status-h" class="flex flex-col gap-0.5" role="group">
            <h3 id="status-h" class="m-0 px-2 pb-1 text-sm font-semibold text-surface-900">Status</h3>

            <button
              v-for="option in statusOptions"
              :key="option.value ?? 'all'"
              :aria-pressed="filters.status === option.value"
              class="flex h-10 items-center gap-3 rounded-card px-3 text-left text-sm font-medium"
              :class="filters.status === option.value ? 'bg-primary-50 text-primary-700 dark:text-primary' : 'text-surface-900 hover:bg-surface-100'"
              type="button"
              @click="setFilters({ status: option.value })"
            >
              <StationStatusMark v-if="option.value" :status="option.value" />
              <span class="grow">{{ option.label }}</span>
              <span class="tabular-nums text-surface-600">{{ option.count }}</span>
            </button>
          </div>

          <StationFilterFields
            class="px-1"
            :facets="facets"
            :filters="filters"
            :show-org="isStaff"
            @change="setFilters"
          />
        </template>

        <!-- A station is open: the list to switch between, the open one highlighted -->
        <template v-else>
          <p v-if="!loading && shown.length === 0" class="m-0 px-2 text-sm text-surface-600">No stations match.</p>

          <ul v-else aria-label="Stations" class="m-0 flex list-none flex-col gap-0.5 p-0">
            <li
              v-for="row in shown"
              :key="row.id"
              class="relative flex items-center gap-3 rounded-card px-3 py-2.5 transition-colors duration-150"
              :class="row.id === routeId ? 'bg-primary-50' : 'hover:bg-surface-100 active:bg-surface-200'"
              @click="keyPress"
              @pointercancel="release"
              @pointerdown="press"
              @pointerleave="release"
              @pointerup="release"
            >
              <span class="grid size-10 shrink-0 place-items-center rounded-card" :class="lookOf(row.status).chip">
                <v-icon :icon="lookOf(row.status).icon" size="20" />
              </span>

              <span class="flex min-w-0 grow flex-col">
                <span class="flex items-baseline justify-between gap-2">
                  <router-link
                    :aria-current="row.id === routeId ? 'page' : undefined"
                    class="min-w-0 truncate font-medium text-surface-900 no-underline after:absolute after:inset-0 after:rounded-card focus-visible:outline-none focus-visible:after:outline-2 focus-visible:after:outline-offset-2 focus-visible:after:outline-primary"
                    :to="{ name: 'stations', params: { id: row.id }, query: listQuery }"
                  >{{ row.name }}</router-link>

                  <span class="shrink-0 font-mono text-xs font-medium text-surface-600">{{ row.code }}</span>
                </span>

                <span class="truncate text-sm text-surface-600">
                  {{ lookOf(row.status).label }} · <template v-if="isStaff">{{ row.owner_org_name }} · </template>{{ countryName(row.country) }}
                </span>
              </span>
            </li>
          </ul>
        </template>
      </div>
    </PaneContent>

    <!-- The view: one station -->
    <template v-if="routeId">
      <FeedbackBanner v-if="detailError" :type="detailError === 'missing' ? 'info' : 'error'">{{ detailMessage }}</FeedbackBanner>

      <div v-else-if="!detail" aria-label="Loading the station…" class="flex flex-col gap-3" role="status">
        <v-skeleton-loader type="heading, list-item-two-line, list-item-two-line, list-item-two-line" />
      </div>

      <StationDetailView v-else :is-staff="isStaff" :station="detail" />
    </template>

    <!-- The view: the list -->
    <div v-else class="flex flex-col gap-5">
      <FeedbackBanner v-if="loadError" type="error">{{ loadError }}</FeedbackBanner>

      <div v-else-if="loading" aria-label="Loading stations…" class="flex flex-col gap-2" role="status">
        <v-skeleton-loader v-for="n in 4" :key="n" type="list-item-two-line" />
      </div>

      <template v-else>
        <!-- Numbers before charts (DBD): each with its words -->
        <div class="flex flex-wrap gap-x-8 gap-y-3 border-b border-surface-200 pb-4">
          <div v-for="kpi in kpis" :key="kpi.label" class="flex flex-col">
            <span class="text-2xl font-semibold tabular-nums text-surface-900">{{ kpi.value }}</span>

            <span class="text-sm text-surface-600">
              {{ kpi.label }}<template v-if="kpi.to"> · <router-link class="font-medium text-primary no-underline hover:underline" :to="kpi.to">{{ kpi.link }}</router-link></template>
            </span>
          </div>
        </div>

        <p v-if="stations.length === 0" class="m-0 py-8 text-center text-surface-600">
          {{ isClient ? 'Your organization has no stations here yet.' : 'No stations yet. They arrive with the station import.' }}
        </p>

        <p v-else-if="shown.length === 0" class="m-0 py-8 text-center text-surface-600">
          No stations match these filters.
          <button class="font-medium text-primary hover:underline" type="button" @click="clearFilters">Clear filters</button>
        </p>

        <!-- From 768 px: a table -->
        <div v-else-if="mdAndUp" class="overflow-x-auto">
          <table class="w-full border-collapse text-sm">
            <caption class="sr-only">Stations, sorted by code</caption>

            <thead>
              <tr class="bg-surface-100 text-left">
                <th class="whitespace-nowrap px-4 py-3 text-xs font-medium text-surface-700" scope="col">Code</th>
                <th class="whitespace-nowrap px-4 py-3 text-xs font-medium text-surface-700" scope="col">Name</th>
                <th class="whitespace-nowrap px-4 py-3 text-xs font-medium text-surface-700" scope="col">Status</th>
                <th v-if="isStaff" class="whitespace-nowrap px-4 py-3 text-xs font-medium text-surface-700" scope="col">Organization</th>
                <th class="whitespace-nowrap px-4 py-3 text-xs font-medium text-surface-700" scope="col">Country</th>
                <th class="whitespace-nowrap px-4 py-3 text-xs font-medium text-surface-700" scope="col">Last visit</th>
                <th class="whitespace-nowrap px-4 py-3 text-xs font-medium text-surface-700" scope="col">Calibration</th>
              </tr>
            </thead>

            <tbody>
              <tr
                v-for="row in shown"
                :key="row.id"
                class="h-13 cursor-pointer border-t border-surface-200 hover:bg-surface-50"
                @click="openFromRow($event, row.id)"
              >
                <td class="whitespace-nowrap px-4">
                  <router-link
                    class="font-mono font-medium text-primary no-underline hover:underline"
                    :to="{ name: 'stations', params: { id: row.id }, query: listQuery }"
                  >{{ row.code }}</router-link>
                </td>

                <td class="px-4 text-surface-900">{{ row.name }}</td>
                <td class="px-4"><StationStatusChip :status="row.status" /></td>
                <td v-if="isStaff" class="whitespace-nowrap px-4 text-surface-900">{{ row.owner_org_name ?? '—' }}</td>
                <td class="whitespace-nowrap px-4 text-surface-900">{{ countryName(row.country) }}</td>

                <td class="whitespace-nowrap px-4 tabular-nums" :class="row.last_visit_at ? 'text-surface-900' : 'text-surface-600'">
                  {{ row.last_visit_at ? formatDate(row.last_visit_at, row.time_zone) : 'None yet' }}
                </td>

                <td class="px-4">
                  <CalibrationDueChip
                    v-if="row.next_calibration_due_at"
                    :due="row.next_calibration_due_at"
                    :state="dueState(row.next_calibration_due_at, now)"
                    :time-zone="row.time_zone"
                  />

                  <span v-else class="text-surface-600">—</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Phones: cards -->
        <ul v-else aria-label="Stations" class="m-0 flex list-none flex-col p-0">
          <li v-for="row in shown" :key="row.id" class="relative flex flex-col gap-1.5 border-t border-surface-200 py-3.5">
            <span class="flex items-start justify-between gap-2">
              <router-link
                class="text-base font-semibold text-surface-900 no-underline after:absolute after:inset-0 focus-visible:outline-none focus-visible:after:outline-2 focus-visible:after:outline-primary"
                :to="{ name: 'stations', params: { id: row.id }, query: listQuery }"
              >{{ row.name }}</router-link>

              <StationStatusChip :status="row.status" />
            </span>

            <span class="font-mono text-xs font-medium text-surface-600">{{ row.code }}</span>

            <span class="text-sm text-surface-600">
              <template v-if="isStaff">{{ row.owner_org_name }} · </template>{{ countryName(row.country) }} · {{ zoneAbbreviation(row.time_zone) }}
            </span>

            <ParameterTags v-if="row.parameters.length > 0" :parameters="row.parameters" />

            <span v-if="dueState(row.next_calibration_due_at, now) === 'overdue'">
              <CalibrationDueChip :due="row.next_calibration_due_at" state="overdue" :time-zone="row.time_zone" />
            </span>
          </li>
        </ul>
      </template>
    </div>

    <!-- Phones: the filters that don't fit in the chip row -->
    <v-bottom-sheet v-model="sheet" aria-labelledby="filters-h">
      <div class="flex flex-col gap-5 rounded-t-card bg-surface px-5 pb-[calc(20px+env(safe-area-inset-bottom))] pt-5">
        <div class="flex items-center justify-between">
          <h2 id="filters-h" class="m-0 text-h2 text-surface-900">Filters</h2>
          <v-btn class="text-primary" variant="text" @click="sheet = false">Done</v-btn>
        </div>

        <StationFilterFields :facets="facets" :filters="filters" :show-org="isStaff" @change="setFilters" />
      </div>
    </v-bottom-sheet>
  </PageBody>
</template>

<script lang="ts" setup>
  import type { StationFilters } from './stations'
  import type { StationDetail, StationSummary } from '@/api/models'
  import { mdiFilterVariant, mdiMagnify } from '@mdi/js'
  import { storeToRefs } from 'pinia'
  import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { useDisplay } from 'vuetify'
  import { calibrationsApi, stationsApi } from '@/api/operations'
  import { ApiError, NetworkError } from '@/api/problem'
  import { countryName } from '@/app/countries'
  import { formatDate, zoneAbbreviation } from '@/app/format'
  import { pressDown, pressPulse, pressUp } from '@/app/motion'
  import { usePaneSelection } from '@/app/shells/pane'
  import CalibrationDueChip from '@/components/CalibrationDueChip.vue'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import PageBody from '@/components/PageBody.vue'
  import PaneContent from '@/components/PaneContent.vue'
  import StationStatusChip from '@/components/StationStatusChip.vue'
  import StationStatusMark from '@/components/StationStatusMark.vue'
  import { useSessionStore } from '@/stores/session'
  import ParameterTags from './ParameterTags.vue'
  import StationDetailView from './StationDetailView.vue'
  import StationFilterFields from './StationFilterFields.vue'
  import {
    dueState,
    extraFilterCount,
    facetsOf,
    filtersFrom,
    lookOf,
    matches,
    matchesOthers,
    queryFrom,
    STATUSES,
    statusLook,
  } from './stations'

  // /stations and /stations/:id (AFD §3; PRD STN-5, CAL-3). Clients see their own organization's
  // stations: the server scopes every query (rule 3), this page only hides staff-only columns.
  // A few hundred stations at most (PRD §2): the page loads them all once and filters here, so the
  // filters answer at once and their counts are exact.
  const session = useSessionStore()
  const { isClient, isStaff } = storeToRefs(session)
  const route = useRoute()
  const router = useRouter()
  const { mdAndUp } = useDisplay()

  const stations = ref<StationSummary[]>([])
  const loading = ref(true)
  const loadError = ref<string | null>(null)
  const overdueUnits = ref<number | null>(null)
  const sheet = ref(false)
  const now = new Date()

  const routeId = computed(() => typeof route.params.id === 'string' && route.params.id ? route.params.id : null)
  usePaneSelection(() => routeId.value !== null)

  // --- Filters (in the URL) ---------------------------------------------------------------------

  const filters = computed(() => filtersFrom(route.query))
  /** The list's query without the station page's own (`tab`), for links back to the list. */
  const listQuery = computed(() => queryFrom(filters.value))
  const facets = computed(() => facetsOf(stations.value))
  const extraFilters = computed(() => extraFilterCount(filters.value))
  const others = computed(() => stations.value.filter(s => matchesOthers(s, filters.value)))
  const shown = computed(() => stations.value.filter(s => matches(s, filters.value)))

  const statusOptions = computed(() => [
    { value: null, label: 'All', count: others.value.length },
    ...STATUSES.map(status => ({
      value: status,
      label: statusLook[status].label,
      count: others.value.filter(s => s.status === status).length,
    })),
  ])

  function setFilters (patch: Partial<StationFilters>): void {
    void router.replace({ query: { ...route.query, ...queryFrom({ ...filters.value, ...patch }) } })
  }

  function clearFilters (): void {
    void router.replace({ query: {} })
  }

  // --- The list's header and numbers ------------------------------------------------------------

  function plural (n: number, one: string, many = `${one}s`): string {
    return `${n} ${n === 1 ? one : many}`
  }

  const summary = computed(() => {
    if (loading.value || loadError.value) {
      return undefined
    }
    const n = stations.value.length
    if (isClient.value) {
      const org = stations.value[0]?.owner_org_name
      return org ? `${org} · ${plural(n, 'station')}` : plural(n, 'station')
    }
    const countries = new Set(stations.value.map(s => s.country)).size
    return `${plural(n, 'station')} in ${plural(countries, 'country', 'countries')}`
  })

  const kpis = computed(() => {
    const all = stations.value
    const list: { label: string, value: number | string, to?: object, link?: string }[] = [
      { label: 'Operational', value: all.filter(s => s.status === 'operational').length },
      { label: 'Degraded or offline', value: all.filter(s => s.status === 'degraded' || s.status === 'offline').length },
    ]
    if (isStaff.value) {
      list.push({
        label: 'Sensors overdue for calibration',
        value: overdueUnits.value ?? '—',
        to: { name: 'calibration' },
        link: 'Calibration list',
      })
    } else {
      // Clients have no unit-level due list: count their stations with a unit overdue
      list.push({
        label: 'Stations with a calibration overdue',
        value: all.filter(s => dueState(s.next_calibration_due_at, now) === 'overdue').length,
      })
    }
    return list
  })

  // --- Loading ----------------------------------------------------------------------------------

  function failure (error: unknown, what: string): string {
    return error instanceof NetworkError
      ? 'This needs a connection. It will load when you have signal.'
      : `We couldn’t load ${what}. Reload the page to try again.`
  }

  async function load (): Promise<void> {
    loading.value = true
    loadError.value = null
    try {
      const all: StationSummary[] = []
      let after: string | undefined
      do {
        const page = await stationsApi.list({ limit: 500, after })
        all.push(...page.items)
        after = page.next_after ?? undefined
      } while (after)
      stations.value = all
    } catch (error) {
      loadError.value = failure(error, 'the stations')
    } finally {
      loading.value = false
    }
    if (isStaff.value) {
      try {
        const due = await calibrationsApi.due(0)
        overdueUnits.value = due.items.filter(u => u.due_state === 'overdue').length
      } catch {
        overdueUnits.value = null // the number shows "—"; the list itself loaded
      }
    }
  }

  // --- One station ------------------------------------------------------------------------------

  const detail = ref<StationDetail | null>(null)
  const detailError = ref<'missing' | 'offline' | 'failed' | null>(null)
  const detailMessage = computed(() => {
    switch (detailError.value) {
      case 'missing': {
        return 'We can’t find this station. It may have been removed, or the link may be wrong.'
      }
      case 'offline': {
        return 'This needs a connection. It will load when you have signal.'
      }
      default: {
        return 'We couldn’t load this station. Reload the page to try again.'
      }
    }
  })
  let detailAbort: AbortController | null = null

  watch(routeId, async id => {
    detailAbort?.abort()
    detailError.value = null
    if (!id) {
      detail.value = null
      return
    }
    if (detail.value?.id !== id) {
      detail.value = null
    }
    const abort = new AbortController()
    detailAbort = abort
    try {
      detail.value = await stationsApi.get(id, abort.signal)
    } catch (error) {
      if (abort.signal.aborted) {
        return
      }
      // Out of scope and missing look the same (ADR-16: 404, not 403)
      detailError.value = error instanceof ApiError && (error.status === 404 || error.status === 422)
        ? 'missing'
        : (error instanceof NetworkError ? 'offline' : 'failed')
    }
  }, { immediate: true })

  onBeforeUnmount(() => detailAbort?.abort())

  // --- Rows -------------------------------------------------------------------------------------

  /** A click anywhere on a table row opens the station; the code link is the keyboard's way. */
  function openFromRow (event: MouseEvent, id: string): void {
    if ((event.target as Element).closest('a, button') || window.getSelection()?.toString()) {
      return
    }
    void router.push({ name: 'stations', params: { id }, query: listQuery.value })
  }

  function press (event: PointerEvent): void {
    if (event.button === 0) {
      pressDown(event.currentTarget as Element)
    }
  }

  function release (event: PointerEvent): void {
    pressUp(event.currentTarget as Element)
  }

  function keyPress (event: MouseEvent): void {
    if (event.detail === 0) {
      pressPulse(event.currentTarget as Element)
    }
  }

  onMounted(load)
</script>
