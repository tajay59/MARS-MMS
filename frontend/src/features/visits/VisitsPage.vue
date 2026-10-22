<template>
  <PageBody
    :back="open ? { name: 'visits', query: listQuery } : undefined"
    back-label="Back to visits"
    :bleed="mdAndUp && !open"
    :record="open ? visitId : null"
    :stacked="Boolean(detail)"
    :subtitle="open ? undefined : summary"
    :title="visitId ? (detail?.ref ?? 'Visit') : undefined"
    :wide="!open"
  >
    <template v-if="detail" #subtitle>
      <VisitStatusChip :status="detail.status" />
      <span v-if="detail.request_title" class="max-md:basis-full">{{ detail.request_title }}</span>

      <router-link
        v-if="detail.request_ref"
        class="font-mono text-xs font-medium text-surface-900"
        :to="{ name: 'requests', params: { id: detail.request_id } }"
        translate="no"
      >{{ detail.request_ref }}</router-link>
    </template>

    <template v-if="detail && mdAndUp && detail.actions.length > 0" #actions>
      <VisitActions
        :busy="busy"
        :visit="detail"
        @cancel="dialog = 'cancel'"
        @end="dialog = 'end'"
        @reschedule="dialog = 'reschedule'"
        @restore="restore"
        @start="start"
      />
    </template>

    <!-- The pane: search and the Mine / All choice; with a visit open, the visits to switch between -->
    <PaneContent pin>
      <div class="flex flex-col gap-4 px-3">
        <v-text-field
          aria-label="Search visits by reference, request or station"
          autocomplete="off"
          class="px-1 [&_.v-field]:bg-surface-50"
          clearable
          flat
          hide-details
          :model-value="q"
          name="q"
          placeholder="Search visits"
          :prepend-inner-icon="mdiMagnify"
          spellcheck="false"
          type="search"
          variant="solo-inverted"
          @update:model-value="setQuery({ q: $event ?? '' })"
        />

        <div v-if="canAttend && canSeeAll" aria-label="Whose visits" class="flex gap-1.5 px-1" role="group">
          <button
            v-for="option in scopes"
            :key="option.value"
            :aria-pressed="scope === option.value"
            class="inline-flex h-8 items-center rounded-full border px-3.5 text-sm font-medium"
            :class="scope === option.value ? 'border-transparent bg-primary-100 text-primary-700 dark:bg-primary-800 dark:text-primary-100' : 'border-surface-300 text-surface-900'"
            type="button"
            @click="setQuery({ scope: option.value })"
          >{{ option.label }}</button>
        </div>

        <template v-if="open">
          <p v-if="!loading && shown.length === 0" class="m-0 px-2 text-sm text-surface-600">No visits match.</p>

          <ul v-else aria-label="Visits" class="m-0 flex list-none flex-col gap-0.5 p-0">
            <li
              v-for="row in shown"
              :key="row.id"
              class="relative flex flex-col gap-1 rounded-card px-3 py-2.5 transition-colors duration-150"
              :class="row.id === visitId ? 'bg-primary-50' : 'hover:bg-surface-100 active:bg-surface-200'"
              @click="keyPress"
              @pointercancel="release"
              @pointerdown="press"
              @pointerleave="release"
              @pointerup="release"
            >
              <span class="flex items-baseline justify-between gap-2">
                <span class="font-mono text-xs font-medium text-surface-600" translate="no">{{ row.ref }}</span>
                <VisitStatusChip :status="row.status" />
              </span>

              <router-link
                :aria-current="row.id === visitId ? 'page' : undefined"
                class="min-w-0 truncate font-medium text-surface-900 no-underline after:absolute after:inset-0 after:rounded-card focus-visible:outline-none focus-visible:after:outline-2 focus-visible:after:outline-offset-2 focus-visible:after:outline-primary"
                :to="{ name: 'visits', params: { id: row.id }, query: listQuery }"
              >{{ row.request_title }}</router-link>

              <span class="text-sm text-surface-600">{{ formatWhen(row.planned_start, visitZone(row)) }}</span>
            </li>
          </ul>
        </template>
      </div>
    </PaneContent>

    <!-- The view: one visit -->
    <template v-if="visitId">
      <FeedbackBanner v-if="detailError" :type="detailError === 'missing' ? 'info' : 'error'">{{ detailMessage }}</FeedbackBanner>

      <div v-else-if="!detail" aria-label="Loading the visit…" class="flex flex-col gap-3" role="status">
        <v-skeleton-loader type="heading, list-item-two-line, list-item-two-line, list-item-two-line" />
      </div>

      <template v-else>
        <!-- Phones: the actions sit under the header, one to a row, as wide as the screen -->
        <div v-if="!mdAndUp && detail.actions.length > 0" class="mb-4 flex flex-col gap-2">
          <VisitActions
            :busy="busy"
            full
            :visit="detail"
            @cancel="dialog = 'cancel'"
            @end="dialog = 'end'"
            @reschedule="dialog = 'reschedule'"
            @restore="restore"
            @start="start"
          />
        </div>

        <VisitDetailView
          :busy="busy"
          :is-admin="session.hasAnyRole(['admin'])"
          :is-client="isClient"
          :me="session.user?.id"
          :pending="pendingMedia"
          :visit="detail"
          @add-media="addingTo = $event"
          @arrive="station('arrive', $event)"
          @change-owner="ownerOf = $event; dialog = 'owner'"
          @changed="adopt"
          @depart="station('depart', $event)"
          @discard-media="uploads?.discard($event)"
          @retry-media="uploads?.retry($event)"
        />
      </template>
    </template>

    <!-- The view: the list -->
    <div v-else class="flex flex-col gap-5 md:h-full md:gap-0">
      <FeedbackBanner v-if="loadError" class="md:m-8" type="error">{{ loadError }}</FeedbackBanner>

      <div v-else-if="loading" aria-label="Loading visits…" class="flex flex-col gap-2 md:px-8 md:py-7" role="status">
        <v-skeleton-loader v-for="n in 4" :key="n" type="list-item-two-line" />
      </div>

      <template v-else>
        <div v-if="visits.length === 0" class="flex flex-col items-center gap-2 py-12 text-center text-surface-600 md:px-8">
          <v-icon :icon="icons.visit" size="48" />
          <p class="m-0 text-h3 text-surface-900">{{ scope === 'mine' && canAttend ? 'No visits for you yet' : 'No visits yet' }}</p>
          <p class="m-0">{{ isClient ? 'When a visit is planned for one of your requests, it appears here.' : 'Schedule a visit from a request you are assigned to.' }}</p>
          <v-btn v-if="!isClient" class="mt-2" color="primary" :to="{ name: 'requests' }">Go to requests</v-btn>
        </div>

        <p v-else-if="shown.length === 0" class="m-0 py-8 text-center text-surface-600 md:px-8">
          No visits match “{{ q }}”.
          <button class="font-medium text-primary hover:underline" type="button" @click="setQuery({ q: '' })">Clear search</button>
        </p>

        <!-- From 768 px: a table -->
        <div v-else-if="mdAndUp" class="min-h-0 grow overflow-auto">
          <table class="w-full border-collapse text-sm">
            <caption class="sr-only">Visits, soonest first</caption>

            <thead>
              <tr class="text-left">
                <th class="sticky top-0 z-10 whitespace-nowrap bg-surface-100 px-3 py-3 text-xs font-medium text-surface-700 first:pl-6 last:pr-6" scope="col">Visit</th>
                <th class="sticky top-0 z-10 whitespace-nowrap bg-surface-100 px-3 py-3 text-xs font-medium text-surface-700 first:pl-6 last:pr-6" scope="col">Request</th>
                <th class="sticky top-0 z-10 whitespace-nowrap bg-surface-100 px-3 py-3 text-xs font-medium text-surface-700 first:pl-6 last:pr-6" scope="col">Status</th>
                <th class="sticky top-0 z-10 whitespace-nowrap bg-surface-100 px-3 py-3 text-xs font-medium text-surface-700 first:pl-6 last:pr-6" scope="col">When</th>
                <th class="sticky top-0 z-10 whitespace-nowrap bg-surface-100 px-3 py-3 text-xs font-medium text-surface-700 first:pl-6 last:pr-6" scope="col">Stations</th>
                <th class="sticky top-0 z-10 whitespace-nowrap bg-surface-100 px-3 py-3 text-xs font-medium text-surface-700 first:pl-6 last:pr-6" scope="col">Lead</th>
              </tr>
            </thead>

            <tbody>
              <tr
                v-for="row in shown"
                :key="row.id"
                class="h-14 cursor-pointer border-t border-surface-200 hover:bg-surface-50"
                @click="openFromRow($event, row.id)"
              >
                <td class="whitespace-nowrap px-3 first:pl-6">
                  <router-link
                    class="font-mono font-medium text-primary no-underline hover:underline"
                    :to="{ name: 'visits', params: { id: row.id }, query: listQuery }"
                    translate="no"
                  >{{ row.ref }}</router-link>
                </td>

                <td class="max-w-64 truncate px-3 font-medium text-surface-900" :title="row.request_title ?? undefined">{{ row.request_title }}</td>
                <td class="px-3"><VisitStatusChip :status="row.status" /></td>
                <td class="whitespace-nowrap px-3 text-surface-900">{{ formatRange(row.planned_start, row.planned_end, visitZone(row)) }}</td>
                <td class="max-w-56 truncate px-3 text-surface-900" :title="stationNames(row)">{{ stationNames(row) }}</td>
                <td class="whitespace-nowrap px-3 text-surface-900 last:pr-6">{{ row.lead.name }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Phones: cards that slide up under the pinned header's curve -->
        <ul v-else aria-label="Visits" class="m-0 flex list-none flex-col gap-1 p-0">
          <VisitCard
            v-for="row in shown"
            :key="row.id"
            :to="{ name: 'visits', params: { id: row.id }, query: listQuery }"
            :visit="row"
          />
        </ul>
      </template>
    </div>

    <CancelVisitDialog
      v-if="detail"
      v-model="cancelOpen"
      :visit="detail"
      @changed="reloadDetail"
      @done="changed('Visit cancelled. Everyone is told.', $event)"
    />

    <RescheduleDialog
      v-if="detail"
      v-model="rescheduleOpen"
      :visit="detail"
      @changed="reloadDetail"
      @done="changed('Visit rescheduled. Everyone is told.', $event)"
    />

    <EndVisitDialog
      v-if="detail"
      v-model="endOpen"
      :visit="detail"
      @changed="reloadDetail"
      @done="ended"
    />

    <ChangeOwnerDialog
      v-if="detail"
      v-model="ownerOpen"
      :station-id="ownerOf"
      :visit="detail"
      @changed="reloadDetail"
      @done="changed('Owner changed. Both people are told.', $event)"
    />

    <AddMediaDialog
      v-if="detail && addingStation"
      :model-value="addingTo !== null"
      :station-code="addingStation.station_code"
      :station-name="addingStation.station_name ?? 'this station'"
      @pick="addFiles"
      @update:model-value="addingTo = null"
    />

    <v-snackbar v-model="toast.show" location="bottom" :timeout="6000">{{ toast.text }}</v-snackbar>
  </PageBody>
</template>

<script lang="ts" setup>
  import type { Phase } from './media'
  import type { VisitOut } from '@/api/models'
  import { mdiMagnify } from '@mdi/js'
  import { storeToRefs } from 'pinia'
  import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { useDisplay } from 'vuetify'
  import { visitsApi } from '@/api/operations'
  import { ApiError, NetworkError } from '@/api/problem'
  import { isVisitUpdate, settled, useLive } from '@/app/composables/useLive'
  import { useVisitMedia } from '@/app/composables/useVisitMedia'
  import { pressDown, pressPulse, pressUp } from '@/app/motion'
  import { usePaneSelection } from '@/app/shells/pane'
  import { icons } from '@/app/theme/icons'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import PageBody from '@/components/PageBody.vue'
  import PaneContent from '@/components/PaneContent.vue'
  import VisitStatusChip from '@/components/VisitStatusChip.vue'
  import { useSessionStore } from '@/stores/session'
  import AddMediaDialog from './AddMediaDialog.vue'
  import CancelVisitDialog from './CancelVisitDialog.vue'
  import ChangeOwnerDialog from './ChangeOwnerDialog.vue'
  import EndVisitDialog from './EndVisitDialog.vue'
  import { failureOf, replaceVisit } from './failures'
  import { forgetMediaLinks } from './mediaLinks'
  import RescheduleDialog from './RescheduleDialog.vue'
  import VisitActions from './VisitActions.vue'
  import VisitCard from './VisitCard.vue'
  import VisitDetailView from './VisitDetailView.vue'
  import { formatRange, formatWhen, matchesVisit, sortVisits, stationNames, visitZone } from './visits'

  // /visits and /visits/:id (AFD §3; PRD VIS-1 to VIS-4, VIS-11). Staff see the visits they attend
  // (and everyone's when they ask); a client sees their organization's. The server scopes every
  // query (rule 3), this page only hides what a person may not do. A few hundred a year at most
  // (PRD §2): the page loads the visits once and searches here.
  const MAX_LOADED = 1000
  const session = useSessionStore()
  const { isClient } = storeToRefs(session)
  const route = useRoute()
  const router = useRouter()
  const { mdAndUp } = useDisplay()

  const visits = ref<VisitOut[]>([])
  const loading = ref(true)
  const loadError = ref<string | null>(null)
  const busy = ref<string | null>(null)
  const toast = reactive({ show: false, text: '' })

  const visitId = computed(() => typeof route.params.id === 'string' && route.params.id ? route.params.id : null)
  const open = computed(() => visitId.value !== null)
  usePaneSelection(() => open.value)

  // Technicians and admins attend visits; a viewer reads them
  const canAttend = computed(() => session.hasAnyRole(['technician', 'admin']))
  const canSeeAll = computed(() => !isClient.value)
  const scopes = [{ value: 'mine', label: 'Mine' }, { value: 'all', label: 'All' }] as const

  function say (text: string): void {
    toast.text = text
    toast.show = true
  }

  // --- The search and the choice of whose, in the URL --------------------------------------------

  const q = computed(() => typeof route.query.q === 'string' ? route.query.q : '')
  const scope = computed<'mine' | 'all'>(() => {
    if (!canAttend.value || isClient.value) {
      return 'all'
    }
    return route.query.scope === 'all' ? 'all' : 'mine'
  })
  const listQuery = computed(() => ({ q: q.value.trim() || undefined, scope: scope.value === 'all' && canAttend.value ? 'all' : undefined }))

  function setQuery (patch: { q?: string, scope?: 'mine' | 'all' }): void {
    const next = { ...listQuery.value, ...patch }
    void router.replace({
      query: { ...route.query, q: next.q?.trim() || undefined, scope: next.scope === 'all' ? 'all' : undefined },
    })
  }

  const shown = computed(() => sortVisits(visits.value.filter(v => matchesVisit(v, q.value))))

  const summary = computed(() => {
    if (loading.value || loadError.value) {
      return undefined
    }
    const n = visits.value.length
    return `${n} ${n === 1 ? 'visit' : 'visits'}`
  })

  // --- Loading ----------------------------------------------------------------------------------

  function failure (error: unknown): string {
    return error instanceof NetworkError
      ? 'This needs a connection. It will load when you have signal.'
      : 'We couldn’t load the visits. Reload the page to try again.'
  }

  async function load (quiet = false): Promise<void> {
    if (!quiet) {
      loading.value = true
      loadError.value = null
    }
    try {
      if (scope.value === 'mine') {
        visits.value = (await visitsApi.mine()).items
      } else {
        const all: VisitOut[] = []
        let after: string | undefined
        do {
          const page = await visitsApi.list({ limit: 200, after })
          all.push(...page.items)
          after = page.next_after ?? undefined
        } while (after && all.length < MAX_LOADED)
        visits.value = all
      }
    } catch (error) {
      // A quiet refresh that fails leaves the list as it is
      if (!quiet) {
        loadError.value = failure(error)
      }
    } finally {
      loading.value = false
    }
  }

  watch(scope, () => {
    void load()
  })

  // --- One visit --------------------------------------------------------------------------------

  const detail = ref<VisitOut | null>(null)
  const detailError = ref<'missing' | 'offline' | 'failed' | null>(null)
  const detailMessage = computed(() => {
    switch (detailError.value) {
      case 'missing': {
        return 'We can’t find this visit. It may have been removed, or the link may be wrong.'
      }
      case 'offline': {
        return 'This needs a connection. It will load when you have signal.'
      }
      default: {
        return 'We couldn’t load this visit. Reload the page to try again.'
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
      detail.value = await visitsApi.get(id, abort.signal)
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

  watch(visitId, id => {
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

  async function reloadDetail (): Promise<void> {
    if (visitId.value) {
      await fetchDetail(visitId.value)
    }
    void load(true)
  }

  /** The list shows what the page just learned: a visit is a list row too. */
  function remember (visit: VisitOut): void {
    detail.value = visit
    visits.value = replaceVisit(visits.value, visit)
  }

  onBeforeUnmount(() => detailAbort?.abort())

  // --- Photos and video: one upload queue for each visit opened, kept while the page is open so a
  // file keeps going up when the person glances at another visit ---------------------------------------

  const latest = new Map<string, VisitOut>()
  const queues = new Map<string, ReturnType<typeof useVisitMedia>>()
  const addingTo = ref<string | null>(null)

  /** The visit as the server holds it after a change made here: the page and the list show it. */
  function adopt (visit: VisitOut): void {
    latest.set(visit.id, visit)
    if (visit.id === visitId.value) {
      detail.value = visit
    }
    visits.value = replaceVisit(visits.value, visit)
  }

  function queueFor (visit: VisitOut) {
    latest.set(visit.id, visit)
    let queue = queues.get(visit.id)
    if (!queue) {
      queue = useVisitMedia({
        visit: () => latest.get(visit.id) ?? visit,
        onVisit: adopt,
      })
      queues.set(visit.id, queue)
    }
    return queue
  }

  const uploads = computed(() => detail.value ? queueFor(detail.value) : null)
  const pendingMedia = computed(() => uploads.value?.items ?? [])
  const addingStation = computed(() => detail.value?.stations.find(s => s.station_id === addingTo.value) ?? null)

  function addFiles (files: File[], phase: Phase): void {
    const stationId = addingTo.value
    if (!uploads.value || !stationId) {
      return
    }
    const refused = uploads.value.add(stationId, phase, files)
    if (refused.length > 0) {
      say(refused.length === 1
        ? `${refused[0]} isn’t a photo or video, so it was left out.`
        : `${refused.length} files weren’t photos or videos, so they were left out.`)
    }
  }

  onBeforeUnmount(() => {
    for (const queue of queues.values()) {
      queue.dispose()
    }
    forgetMediaLinks()
  })

  // --- Actions: the dialogs, and the moves that need no form ---------------------------------------

  const dialog = ref<'cancel' | 'reschedule' | 'end' | 'owner' | null>(null)
  const ownerOf = ref<string | null>(null)

  function dialogModel (kind: 'cancel' | 'reschedule' | 'end' | 'owner') {
    return computed({
      get: () => dialog.value === kind,
      set: (value: boolean) => {
        if (!value && dialog.value === kind) {
          dialog.value = null
        }
      },
    })
  }

  const cancelOpen = dialogModel('cancel')
  const rescheduleOpen = dialogModel('reschedule')
  const endOpen = dialogModel('end')
  const ownerOpen = dialogModel('owner')

  function changed (text: string, visit: VisitOut): void {
    remember(visit)
    say(text)
  }

  function ended (visit: VisitOut): void {
    changed(visit.additional_visit_required
      ? 'Visit ended. The request is back to Assigned for another visit.'
      : 'Visit ended.', visit)
  }

  async function move (key: string, run: () => Promise<VisitOut>, said: string): Promise<void> {
    if (busy.value) {
      return
    }
    busy.value = key
    try {
      changed(said, await run())
    } catch (error) {
      const result = failureOf(error, 'We couldn’t do that. Try again in a moment.')
      say(result.message)
      if (result.reload) {
        await reloadDetail()
      }
    } finally {
      busy.value = null
    }
  }

  async function start (): Promise<void> {
    if (detail.value) {
      const id = detail.value.id
      await move('start', () => visitsApi.start(id), 'Visit started. The request is In progress.')
    }
  }

  async function restore (): Promise<void> {
    if (detail.value) {
      const id = detail.value.id
      await move('restore', () => visitsApi.restore(id), 'Visit restored to planned.')
    }
  }

  async function station (kind: 'arrive' | 'depart', stationId: string): Promise<void> {
    if (detail.value) {
      const id = detail.value.id
      await move(`${kind}-${stationId}`, () => visitsApi[kind](id, stationId), kind === 'arrive' ? 'Arrival recorded.' : 'Departure recorded.')
    }
  }

  // --- Rows -------------------------------------------------------------------------------------

  /** A click anywhere on a table row opens the visit; the reference link is the keyboard's way. */
  function openFromRow (event: MouseEvent, id: string): void {
    if ((event.target as Element).closest('a, button') || window.getSelection()?.toString()) {
      return
    }
    void router.push({ name: 'visits', params: { id }, query: listQuery.value })
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

  // --- Live (PRD NOT-5): the list and the open visit follow changes made elsewhere -----------------

  const refreshList = settled(() => {
    void load(true)
  })
  const refreshOpen = settled(() => {
    if (visitId.value) {
      void fetchDetail(visitId.value)
    }
  })

  useLive(event => {
    if (event.entity === 'reconnected') {
      refreshList()
      refreshOpen()
    } else if (isVisitUpdate(event)) {
      refreshList()
      if (event.id === visitId.value) {
        refreshOpen()
      }
    }
  })

  onMounted(() => load())
</script>
