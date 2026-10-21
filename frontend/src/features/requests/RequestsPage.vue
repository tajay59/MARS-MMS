<template>
  <PageBody
    :back="isNew ? { name: 'requests', query: listQuery } : (editing && requestId ? { name: 'requests', params: { id: requestId }, query: listQuery } : (open ? { name: 'requests', query: listQuery } : undefined))"
    :back-label="editing ? 'Back to the request' : 'Back to requests'"
    :record="open ? (editing ? `${routeId}/edit` : routeId) : null"
    :stacked="Boolean(detail) && !editing"
    :subtitle="open ? undefined : summary"
    :title="isNew ? 'New request' : (editing ? 'Edit request' : (requestId ? (detail?.title ?? 'Request') : undefined))"
    :wide="!open"
  >
    <template v-if="detail && !editing" #subtitle>
      <span class="font-mono font-medium text-surface-900" translate="no">{{ detail.ref }}</span>
      <RequestStatusChip :status="detail.status" />
      <PriorityChip :priority="detail.priority" />
      <span class="max-md:basis-full">{{ headline(detail) }}</span>
    </template>

    <!-- The list: clients report a problem, admins raise a request; technicians and viewers read -->
    <template v-if="!open && canCreate" #actions>
      <v-btn color="primary" :prepend-icon="isClient ? undefined : mdiPlus" :to="{ name: 'request-new' }">{{ isClient ? 'Report a problem' : 'New request' }}</v-btn>
    </template>

    <!-- A request: what the server says this person may do, and nothing else (hidden, not disabled) -->
    <template v-else-if="detail && !editing && mdAndUp && hasActions" #actions>
      <RequestActions
        :busy="busy"
        :detail="detail"
        @approve="approve"
        @assign="assignOpen = true"
        @cancel="decision = 'cancel'"
        @claim="claim"
        @deny="decision = 'deny'"
        @release="letGo"
      />
    </template>

    <!-- The pane: search and filters for the list; with a request open, the requests to switch to -->
    <PaneContent pin>
      <div class="flex flex-col gap-4 px-3">
        <v-text-field
          aria-label="Search requests by reference, title or station"
          autocomplete="off"
          class="px-1"
          clearable
          hide-details
          :model-value="filters.q"
          name="q"
          placeholder="Search reference or title"
          :prepend-inner-icon="mdiMagnify"
          spellcheck="false"
          type="search"
          @update:model-value="setFilters({ q: $event ?? '' })"
        />

        <!-- Phones: status as a row of chips, the rest in a sheet -->
        <div v-if="!open && !mdAndUp" aria-label="Filter by status" class="-mx-3 flex gap-1.5 overflow-x-auto px-4 pb-3 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden" role="group">
          <button
            v-for="option in statusOptions"
            :key="option.value ?? 'all'"
            :aria-pressed="filters.status === option.value"
            class="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-full border px-3 text-sm font-medium"
            :class="filters.status === option.value ? 'border-transparent bg-primary-100 text-primary-700 dark:bg-primary-800 dark:text-primary-100' : 'border-surface-300 text-surface-900'"
            type="button"
            @click="setFilters({ status: option.value })"
          >
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
        <template v-else-if="!open">
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
              <span v-if="option.value" aria-hidden="true" class="grid size-5.5 shrink-0 place-items-center rounded-full" :class="lookOf(option.value).dot">
                <v-icon :icon="lookOf(option.value).icon" size="14" />
              </span>

              <span v-else class="size-5.5 shrink-0" />
              <span class="grow">{{ option.label }}</span>
              <span class="tabular-nums text-surface-600">{{ option.count }}</span>
            </button>
          </div>

          <RequestFilterFields
            class="px-1"
            :facets="facets"
            :filters="filters"
            :show-org="isStaff"
            @change="setFilters"
          />
        </template>

        <!-- A request is open: the list to switch between, the open one highlighted -->
        <template v-else>
          <p v-if="!loading && shown.length === 0" class="m-0 px-2 text-sm text-surface-600">No requests match.</p>

          <ul v-else aria-label="Requests" class="m-0 flex list-none flex-col gap-0.5 p-0">
            <li
              v-for="row in shown"
              :key="row.id"
              class="relative flex flex-col gap-1 rounded-card px-3 py-2.5 transition-colors duration-150"
              :class="row.id === requestId ? 'bg-primary-50' : 'hover:bg-surface-100 active:bg-surface-200'"
              @click="keyPress"
              @pointercancel="release"
              @pointerdown="press"
              @pointerleave="release"
              @pointerup="release"
            >
              <span class="flex items-baseline justify-between gap-2">
                <span class="font-mono text-xs font-medium text-surface-600" translate="no">{{ row.ref }}</span>
                <RequestStatusChip :status="row.status" />
              </span>

              <router-link
                :aria-current="row.id === requestId ? 'page' : undefined"
                class="min-w-0 truncate font-medium text-surface-900 no-underline after:absolute after:inset-0 after:rounded-card focus-visible:outline-none focus-visible:after:outline-2 focus-visible:after:outline-offset-2 focus-visible:after:outline-primary"
                :to="{ name: 'requests', params: { id: row.id }, query: listQuery }"
              >{{ row.title }}</router-link>
            </li>
          </ul>
        </template>
      </div>
    </PaneContent>

    <!-- The view: the form for a new request, or to edit one -->
    <RequestForm
      v-if="isNew"
      ref="formEl"
      :is-admin="isAdmin"
      :preselect="preselect"
      :stations="directory.stations"
      @cancel="router.push({ name: 'requests', query: listQuery })"
      @saved="saved"
    />

    <!-- The view: one request -->
    <template v-else-if="requestId">
      <FeedbackBanner v-if="detailError" :type="detailError === 'missing' ? 'info' : 'error'">{{ detailMessage }}</FeedbackBanner>

      <div v-else-if="!detail" aria-label="Loading the request…" class="flex flex-col gap-3" role="status">
        <v-skeleton-loader type="heading, list-item-two-line, list-item-two-line, list-item-two-line" />
      </div>

      <RequestForm
        v-else-if="editing"
        :key="`${detail.id}-${formKey}`"
        ref="formEl"
        :is-admin="isAdmin"
        :request="detail"
        :stations="directory.stations"
        @cancel="router.push({ name: 'requests', params: { id: detail.id }, query: listQuery })"
        @reload="reloadDetail"
        @saved="saved"
      />

      <template v-else>
        <!-- Phones: the actions sit under the header, one to a row, as wide as the screen -->
        <div v-if="!mdAndUp && hasActions" class="mb-4 flex flex-col gap-2">
          <RequestActions
            :busy="busy"
            :detail="detail"
            full
            @approve="approve"
            @assign="assignOpen = true"
            @cancel="decision = 'cancel'"
            @claim="claim"
            @deny="decision = 'deny'"
            @release="letGo"
          />
        </div>

        <RequestDetailView :detail="detail" :is-client="isClient" />
      </template>
    </template>

    <!-- The view: the list -->
    <div v-else class="flex flex-col gap-5">
      <FeedbackBanner v-if="loadError" type="error">{{ loadError }}</FeedbackBanner>

      <div v-else-if="loading" aria-label="Loading requests…" class="flex flex-col gap-2" role="status">
        <v-skeleton-loader v-for="n in 4" :key="n" type="list-item-two-line" />
      </div>

      <template v-else>
        <FeedbackBanner v-if="capped" type="info">Showing the newest {{ MAX_LOADED }} requests. Search or filter to find an older one.</FeedbackBanner>

        <div v-if="requests.length === 0" class="flex flex-col items-center gap-2 py-12 text-center text-surface-600">
          <v-icon :icon="icons.request" size="48" />
          <p class="m-0 text-h3 text-surface-900">{{ isClient ? 'No requests yet' : 'No requests yet' }}</p>
          <p class="m-0">{{ isClient ? 'When a station has a problem, report it here and follow it until it is fixed.' : 'Requests from clients and ones you raise appear here.' }}</p>
          <v-btn v-if="canCreate" class="mt-2" color="primary" :to="{ name: 'request-new' }">{{ isClient ? 'Report a problem' : 'New request' }}</v-btn>
        </div>

        <p v-else-if="shown.length === 0" class="m-0 py-8 text-center text-surface-600">
          No requests match these filters.
          <button class="font-medium text-primary hover:underline" type="button" @click="clearFilters">Clear filters</button>
        </p>

        <!-- From 768 px: a table -->
        <div v-else-if="mdAndUp" class="overflow-x-auto">
          <table class="w-full border-collapse text-sm">
            <caption class="sr-only">Requests, newest first</caption>

            <thead>
              <tr class="bg-surface-100 text-left">
                <th class="whitespace-nowrap px-3 py-3 text-xs font-medium text-surface-700" scope="col">Reference</th>
                <th class="whitespace-nowrap px-3 py-3 text-xs font-medium text-surface-700" scope="col">Title</th>
                <th class="whitespace-nowrap px-3 py-3 text-xs font-medium text-surface-700" scope="col">Status</th>
                <th class="whitespace-nowrap px-3 py-3 text-xs font-medium text-surface-700" scope="col">Priority</th>
                <th class="whitespace-nowrap px-3 py-3 text-xs font-medium text-surface-700" scope="col">Stations</th>
                <th v-if="isStaff" class="whitespace-nowrap px-3 py-3 text-xs font-medium text-surface-700" scope="col">Organization</th>
                <th class="whitespace-nowrap px-3 py-3 text-xs font-medium text-surface-700" scope="col">Assigned</th>
                <th class="whitespace-nowrap px-3 py-3 text-xs font-medium text-surface-700" scope="col">Updated</th>
              </tr>
            </thead>

            <tbody>
              <tr
                v-for="row in shown"
                :key="row.id"
                class="h-14 cursor-pointer border-t border-surface-200 hover:bg-surface-50"
                @click="openFromRow($event, row.id)"
              >
                <td class="whitespace-nowrap px-3">
                  <router-link
                    class="font-mono font-medium text-primary no-underline hover:underline"
                    :to="{ name: 'requests', params: { id: row.id }, query: listQuery }"
                    translate="no"
                  >{{ row.ref }}</router-link>
                </td>

                <td class="max-w-64 truncate px-3 font-medium text-surface-900" :title="row.title">{{ row.title }}</td>
                <td class="px-3"><RequestStatusChip :status="row.status" /></td>
                <td class="px-3"><PriorityChip v-if="showsInList(row.priority)" :priority="row.priority" /><span v-else class="text-surface-500">·</span></td>
                <td class="whitespace-nowrap px-3 font-mono text-xs font-medium text-surface-900" translate="no">{{ stationsLabel(row) }}</td>
                <td v-if="isStaff" class="max-w-36 truncate px-3 text-surface-900" :title="row.org_name ?? undefined">{{ row.org_name ?? '—' }}</td>
                <td class="whitespace-nowrap px-3" :class="row.assigned_staff.length > 0 ? 'text-surface-900' : 'text-surface-600'">{{ assignedText(row) }}</td>
                <td class="whitespace-nowrap px-3 tabular-nums text-surface-600">{{ formatListTime(row.updated_at) }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Phones: cards that slide up under the pinned header's curve -->
        <ul v-else aria-label="Requests" class="m-0 flex list-none flex-col gap-1 p-0">
          <RequestCard
            v-for="row in shown"
            :key="row.id"
            :is-staff="isStaff"
            :request="row"
            :to="{ name: 'requests', params: { id: row.id }, query: listQuery }"
          />
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

        <RequestFilterFields :facets="facets" :filters="filters" :show-org="isStaff" @change="setFilters" />
      </div>
    </v-bottom-sheet>

    <RequestDecisionDialog
      v-if="detail"
      v-model="decisionOpen"
      :mode="decision ?? 'deny'"
      :reason-required="reasonRequired"
      :request="detail"
      @changed="reloadDetail"
      @done="decided"
    />

    <AssignDialog
      v-if="detail"
      v-model="assignOpen"
      :request="{ ...detail, stationCode: stationsLabel(detail) }"
      @changed="reloadDetail"
      @done="assigned"
    />

    <v-snackbar v-model="toast.show" location="bottom" :timeout="6000">{{ toast.text }}</v-snackbar>
  </PageBody>
</template>

<script lang="ts" setup>
  import type { RequestFilters } from './requests'
  import type { StaffingResult } from './staffingActions'
  import type { RequestDetail, RequestSummary } from '@/api/models'
  import { mdiFilterVariant, mdiMagnify, mdiPlus } from '@mdi/js'
  import { storeToRefs } from 'pinia'
  import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
  import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
  import { useDisplay } from 'vuetify'
  import { requestsApi } from '@/api/operations'
  import { ApiError, NetworkError } from '@/api/problem'
  import { isRequestUpdate, settled, useLive } from '@/app/composables/useLive'
  import { countryName } from '@/app/countries'
  import { formatListTime } from '@/app/format'
  import { pressDown, pressPulse, pressUp } from '@/app/motion'
  import { usePaneSelection } from '@/app/shells/pane'
  import { icons } from '@/app/theme/icons'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import PageBody from '@/components/PageBody.vue'
  import PaneContent from '@/components/PaneContent.vue'
  import RequestStatusChip from '@/components/RequestStatusChip.vue'
  import { useSessionStore } from '@/stores/session'
  import { useStationDirectory } from '@/stores/stationDirectory'
  import AssignDialog from './AssignDialog.vue'
  import PriorityChip from './PriorityChip.vue'
  import RequestActions from './RequestActions.vue'
  import RequestCard from './RequestCard.vue'
  import RequestDecisionDialog from './RequestDecisionDialog.vue'
  import RequestDetailView from './RequestDetailView.vue'
  import RequestFilterFields from './RequestFilterFields.vue'
  import RequestForm from './RequestForm.vue'
  import {
    can,
    extraFilterCount,
    facetsOf,
    filtersFrom,
    joinNames,
    lookOf,
    matches,
    matchesOthers,
    queryFrom,
    showsInList,
    stationsLabel,
    STATUSES,
  } from './requests'
  import { claimRequest, releaseRequest } from './staffingActions'

  // /requests, /requests/new and /requests/:id (AFD §3; PRD REQ-1 to REQ-16). A client sees their
  // organization's requests only: the server scopes every query (rule 3), this page only hides
  // staff-only columns. A few hundred a year at most (PRD §2): the page loads the newest ones once
  // and filters here, so the filters answer at once and their counts are exact.
  const MAX_LOADED = 1000
  const session = useSessionStore()
  const { isClient, isStaff } = storeToRefs(session)
  const route = useRoute()
  const router = useRouter()
  const { mdAndUp } = useDisplay()
  const directory = useStationDirectory()

  const requests = ref<RequestSummary[]>([])
  const loading = ref(true)
  const loadError = ref<string | null>(null)
  const capped = ref(false)
  const sheet = ref(false)
  const busy = ref<'approve' | 'claim' | 'release' | null>(null)
  const assignOpen = ref(false)
  const toast = reactive({ show: false, text: '' })
  const now = new Date()

  // :id is a request's ID, or "new" (the form); :mode is "edit" (REQ-11)
  const routeId = computed(() => route.name === 'request-new' ? 'new' : (typeof route.params.id === 'string' && route.params.id ? route.params.id : null))
  const isNew = computed(() => routeId.value === 'new')
  const requestId = computed(() => isNew.value ? null : routeId.value)
  const editing = computed(() => route.params.mode === 'edit' && requestId.value !== null)
  /** Something is open in the view (a request or the form): phones show it alone. */
  const open = computed(() => routeId.value !== null)
  usePaneSelection(() => open.value)

  // Clients and admins make requests; technicians and viewers read them (the server refuses the rest)
  const isAdmin = computed(() => session.hasAnyRole(['admin']))
  const canCreate = computed(() => session.hasAnyRole(['client', 'admin']))
  const preselect = computed(() => {
    const station = route.query.station
    return typeof station === 'string' ? [station] : []
  })

  function say (text: string): void {
    toast.text = text
    toast.show = true
  }

  // --- Filters (in the URL) ---------------------------------------------------------------------

  const filters = computed(() => filtersFrom(route.query))
  /** The list's query without the page's own (`tab`, `station`), for links back to the list. */
  const listQuery = computed(() => queryFrom(filters.value))
  const facets = computed(() => facetsOf(requests.value))
  const extraFilters = computed(() => extraFilterCount(filters.value))
  const others = computed(() => requests.value.filter(r => matchesOthers(r, filters.value, now)))
  const shown = computed(() => requests.value.filter(r => matches(r, filters.value, now)))

  const statusOptions = computed(() => [
    { value: null, label: 'All', count: others.value.length },
    ...STATUSES.map(status => ({
      value: status,
      label: lookOf(status).label,
      count: others.value.filter(r => r.status === status).length,
    })),
  ])

  // The route updates only when a navigation finishes. A second change made before then (a click on
  // a status and straight away typing a search) must build on the first, not on the old URL.
  let pendingFilters: RequestFilters | null = null

  function setFilters (patch: Partial<RequestFilters>): void {
    const next = { ...(pendingFilters ?? filters.value), ...patch }
    pendingFilters = next
    void router.replace({ query: { ...route.query, ...queryFrom(next) } }).finally(() => {
      if (pendingFilters === next) {
        pendingFilters = null
      }
    })
  }

  function clearFilters (): void {
    void router.replace({ query: {} })
  }

  watch([canCreate, open, editing], () => {
    if (session.ready && !canCreate.value && isNew.value) {
      void router.replace({ name: 'requests', query: listQuery.value })
    }
  }, { immediate: true })

  // --- The list's header ------------------------------------------------------------------------

  function plural (n: number, one: string, many = `${one}s`): string {
    return `${n} ${n === 1 ? one : many}`
  }

  const summary = computed(() => {
    if (loading.value || loadError.value) {
      return undefined
    }
    const n = requests.value.length
    if (isClient.value) {
      const org = requests.value[0]?.org_name
      return org ? `${org} · ${plural(n, 'request')}` : plural(n, 'request')
    }
    const orgs = new Set(requests.value.map(r => r.org_id)).size
    return `${plural(n, 'request')} · ${plural(orgs, 'organization')}`
  })

  /** `Organization A · Jamaica · 2 stations` under a request's title. */
  function headline (r: RequestSummary): string {
    const countries = [...new Set(r.stations.map(s => countryName(s.country)))]
    return [isStaff.value ? r.org_name : null, countries.join(', ') || null, plural(r.stations.length, 'station')]
      .filter(Boolean)
      .join(' · ')
  }

  function assignedText (r: RequestSummary): string {
    if (r.assigned_staff.length > 0) {
      return r.assigned_staff.map(p => p.name).join(', ')
    }
    return ['closed', 'denied', 'cancelled', 'submitted'].includes(r.status) ? '·' : 'Unassigned'
  }

  // --- Loading ----------------------------------------------------------------------------------

  function failure (error: unknown, what: string): string {
    return error instanceof NetworkError
      ? 'This needs a connection. It will load when you have signal.'
      : `We couldn’t load ${what}. Reload the page to try again.`
  }

  async function load (quiet = false): Promise<void> {
    if (!quiet) {
      loading.value = true
      loadError.value = null
    }
    try {
      const all: RequestSummary[] = []
      let after: string | undefined
      do {
        const page = await requestsApi.list({ limit: 200, after })
        all.push(...page.items)
        after = page.next_after ?? undefined
      } while (after && all.length < MAX_LOADED)
      capped.value = Boolean(after)
      requests.value = all
    } catch (error) {
      // A quiet refresh that fails leaves the list as it is
      if (!quiet) {
        loadError.value = failure(error, 'the requests')
      }
    } finally {
      loading.value = false
    }
  }

  // --- One request ------------------------------------------------------------------------------

  const detail = ref<RequestDetail | null>(null)
  const detailError = ref<'missing' | 'offline' | 'failed' | null>(null)
  const detailMessage = computed(() => {
    switch (detailError.value) {
      case 'missing': {
        return 'We can’t find this request. It may have been removed, or the link may be wrong.'
      }
      case 'offline': {
        return 'This needs a connection. It will load when you have signal.'
      }
      default: {
        return 'We couldn’t load this request. Reload the page to try again.'
      }
    }
  })
  let detailAbort: AbortController | null = null

  async function fetchDetail (id: string): Promise<void> {
    detailAbort?.abort()
    detailError.value = null
    const abort = new AbortController()
    detailAbort = abort
    try {
      detail.value = await requestsApi.get(id, abort.signal)
    } catch (error) {
      if (abort.signal.aborted) {
        return
      }
      // Out of scope and missing look the same (ADR-16: 404, not 403)
      detailError.value = error instanceof ApiError && (error.status === 404 || error.status === 422)
        ? 'missing'
        : (error instanceof NetworkError ? 'offline' : 'failed')
    }
  }

  watch(requestId, id => {
    if (!id) {
      detailAbort?.abort()
      detailError.value = null
      detail.value = null
      return
    }
    if (detail.value?.id !== id) {
      detail.value = null
    }
    void fetchDetail(id)
  }, { immediate: true })

  const hasActions = computed(() => Boolean(detail.value) && (detail.value?.actions.length ?? 0) > 0)

  // An edit link for a request that can't be edited any more goes back to the request
  watch([detail, editing], () => {
    if (detail.value && editing.value && !can(detail.value, 'edit')) {
      void router.replace({ name: 'requests', params: { id: detail.value.id }, query: listQuery.value })
    }
  })

  /** The list shows what the page just learned: a request is a request summary too. */
  function remember (request: RequestDetail): void {
    detail.value = request
    const at = requests.value.findIndex(r => r.id === request.id)
    if (at === -1) {
      requests.value = [request, ...requests.value]
    } else {
      requests.value[at] = request
    }
  }

  // --- Approve, deny, cancel (REQ-6, REQ-11) -----------------------------------------------------

  const decision = ref<'deny' | 'cancel' | null>(null)
  const decisionOpen = computed({
    get: () => decision.value !== null,
    set: value => {
      if (!value) {
        decision.value = null
      }
    },
  })
  // An admin must say why once work is planned or under way (the server checks it too)
  const reasonRequired = computed(() => decision.value === 'deny'
    || (decision.value === 'cancel' && ['scheduled', 'in_progress', 'client_review'].includes(detail.value?.status ?? '')))

  async function approve (): Promise<void> {
    if (!detail.value || busy.value) {
      return
    }
    busy.value = 'approve'
    try {
      remember(await requestsApi.approve(detail.value.id))
      say('Request approved. It is now in the queue.')
    } catch (error) {
      if (error instanceof NetworkError) {
        say('You’re offline. Requests need a connection.')
      } else if (error instanceof ApiError && (error.code === 'request_changed' || error.code === 'bad_transition')) {
        say('Someone else just changed this request. It has been reloaded.')
        await reloadDetail()
      } else {
        say('We couldn’t approve it. Try again in a moment.')
      }
    } finally {
      busy.value = null
    }
  }

  // --- Claim, assign, release (REQ-7) -------------------------------------------------------------

  async function claim (): Promise<void> {
    await staffing('claim', claimRequest, request => `You claimed ${request.ref}. Admins have been told.`)
  }

  async function letGo (): Promise<void> {
    await staffing('release', releaseRequest, request => (
      request.status === 'approved' ? `${request.ref} is back in the queue.` : 'You are off this request.'
    ))
  }

  async function staffing (
    kind: 'claim' | 'release', run: (id: string) => Promise<StaffingResult>, said: (request: RequestDetail) => string,
  ): Promise<void> {
    if (!detail.value || busy.value) {
      return
    }
    busy.value = kind
    const result = await run(detail.value.id)
    busy.value = null
    if (result.ok) {
      remember(result.detail)
      say(said(result.detail))
    } else {
      say(result.message)
      if (result.reload) {
        await reloadDetail()
      }
    }
  }

  function assigned (request: RequestDetail): void {
    remember(request)
    say(`${request.ref} is assigned to ${joinNames(request.assigned_staff.map(p => p.name))}.`)
  }

  function decided (request: RequestDetail): void {
    remember(request)
    say(request.status === 'denied' ? 'Request denied. The client can see your reason.' : 'Request cancelled.')
  }

  // --- The form (REQ-1, REQ-2, REQ-11) -----------------------------------------------------------

  const formEl = ref<InstanceType<typeof RequestForm> | null>(null)
  /** Bumped to start the edit form over with the request as it is now. */
  const formKey = ref(0)

  async function reloadDetail (): Promise<void> {
    if (requestId.value) {
      await fetchDetail(requestId.value)
      formKey.value++
    }
  }

  // The form picks stations from the ones the person may see, loaded once per login
  watch([isNew, editing], ([creating, changing]) => {
    if ((creating || changing) && session.user) {
      void directory.load(session.user.id)
    }
  }, { immediate: true })

  /** The request as saved goes into the list and its page. */
  function saved (request: RequestDetail): void {
    const wasNew = isNew.value
    remember(request)
    say(wasNew ? `Request submitted. Your reference is ${request.ref}.` : 'Changes saved.')
    void router.push({ name: 'requests', params: { id: request.id }, query: listQuery.value })
  }

  // A form with unsaved changes asks before the person leaves it (another request, another page)
  async function allowLeave (): Promise<boolean> {
    return (await formEl.value?.confirmLeave()) ?? true
  }

  onBeforeRouteLeave(allowLeave)
  onBeforeRouteUpdate(async (to, from) => {
    // Filters in the URL change on this page without leaving the form; anything else asks
    return to.params.id === from.params.id && to.params.mode === from.params.mode && to.name === from.name ? true : await allowLeave()
  })

  onBeforeUnmount(() => detailAbort?.abort())

  // --- Rows -------------------------------------------------------------------------------------

  /** A click anywhere on a table row opens the request; the reference link is the keyboard's way. */
  function openFromRow (event: MouseEvent, id: string): void {
    if ((event.target as Element).closest('a, button') || window.getSelection()?.toString()) {
      return
    }
    void router.push({ name: 'requests', params: { id }, query: listQuery.value })
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

  // --- Live (PRD NOT-5): the list and the open request follow changes made elsewhere ---------------

  const refreshList = settled(() => {
    void load(true)
  })
  const refreshOpen = settled(() => {
    if (requestId.value && !editing.value) {
      void fetchDetail(requestId.value)
    }
  })

  useLive(event => {
    if (event.entity === 'reconnected') {
      refreshList()
      refreshOpen()
    } else if (isRequestUpdate(event)) {
      refreshList()
      if (event.id === requestId.value) {
        refreshOpen()
      }
    }
  })

  onMounted(() => load())
</script>
