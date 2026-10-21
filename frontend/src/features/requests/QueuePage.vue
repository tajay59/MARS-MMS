<template>
  <PageBody :bleed="mdAndUp" :subtitle="subtitle" title="Queue" wide>
    <!-- Desktop: search and filters are in the pane. Phones: a sheet opened from here, and the badge counts what is on -->
    <PaneContent v-if="mdAndUp">
      <QueueFilterPanel
        class="px-3"
        :filtered="filtered"
        :filters="filters"
        :groups="groups"
        tables
        @change="setFilters"
        @clear="clearFilters"
      />
    </PaneContent>

    <template v-if="!mdAndUp" #actions>
      <v-badge color="primary" :content="activeCount" floating :model-value="activeCount > 0">
        <v-btn
          :aria-label="activeCount > 0 ? `Search and filter the queue, ${activeCount} on` : 'Search and filter the queue'"
          icon
          size="40"
          variant="text"
          @click="filterOpen = true"
        >
          <v-icon :icon="mdiMagnify" />
        </v-btn>
      </v-badge>
    </template>

    <FeedbackBanner v-if="loadError" class="md:m-8" type="error">{{ loadError }}</FeedbackBanner>

    <div v-else-if="loading" aria-label="Loading the queue…" class="flex flex-col gap-2 md:px-8 md:py-7" role="status">
      <v-skeleton-loader v-for="n in 4" :key="n" type="list-item-two-line" />
    </div>

    <template v-else>
      <div v-if="items.length === 0" class="flex flex-col items-center gap-2 py-12 text-center text-surface-600 md:px-8">
        <v-icon :icon="mdiInboxOutline" size="48" />
        <p class="m-0 text-h3 text-surface-900">The queue is empty</p>
        <p class="m-0">Approved requests that nobody has taken show up here.</p>
      </div>

      <p v-else-if="shown.length === 0" class="m-0 py-8 text-center text-surface-600 md:px-8">
        Nothing in the queue matches.
        <button class="font-medium text-primary hover:underline" type="button" @click="clearFilters">Clear filters</button>
      </p>

      <!-- From 768 px: a table, oldest approval first -->
      <div v-else-if="mdAndUp" class="h-full overflow-auto">
        <table class="w-full border-collapse text-sm">
          <caption class="sr-only">Approved requests waiting for someone, oldest first</caption>

          <thead>
            <tr class="text-left">
              <th class="sticky top-0 z-10 whitespace-nowrap bg-surface-100 px-3 py-3 text-xs font-medium text-surface-700 first:pl-6" scope="col">Reference</th>
              <th class="sticky top-0 z-10 whitespace-nowrap bg-surface-100 px-3 py-3 text-xs font-medium text-surface-700 first:pl-6" scope="col">Request</th>
              <th class="sticky top-0 z-10 whitespace-nowrap bg-surface-100 px-3 py-3 text-xs font-medium text-surface-700 first:pl-6" scope="col">Organization</th>
              <th class="sticky top-0 z-10 whitespace-nowrap bg-surface-100 px-3 py-3 text-xs font-medium text-surface-700 first:pl-6" scope="col">Country</th>
              <th class="sticky top-0 z-10 whitespace-nowrap bg-surface-100 px-3 py-3 text-xs font-medium text-surface-700 first:pl-6" scope="col">Priority</th>
              <th class="sticky top-0 z-10 whitespace-nowrap bg-surface-100 px-3 py-3 text-xs font-medium text-surface-700 first:pl-6" scope="col">Waiting</th>
              <th class="sticky top-0 z-10 bg-surface-100 px-3 py-3 text-right text-xs font-medium text-surface-700 last:pr-6" scope="col"><span class="sr-only">Actions</span></th>
            </tr>
          </thead>

          <tbody>
            <tr v-for="row in shown" :key="row.id" class="h-15 border-t border-surface-200">
              <td class="whitespace-nowrap px-3 font-mono text-xs font-medium text-surface-600 first:pl-6" translate="no">{{ row.ref }}</td>

              <td class="max-w-80 px-3">
                <router-link class="block truncate font-medium text-surface-900 no-underline hover:underline" :title="row.title" :to="{ name: 'requests', params: { id: row.id } }">{{ row.title }}</router-link>
                <span class="block truncate font-mono text-xs font-medium text-surface-600" translate="no">{{ stationsLabel(row) }} · {{ categoryLabel(row.category) }}</span>
              </td>

              <td class="max-w-40 truncate px-3 text-surface-900" :title="row.org_name ?? undefined">{{ row.org_name ?? '—' }}</td>
              <td class="whitespace-nowrap px-3 text-surface-900">{{ countriesOf(row) }}</td>
              <td class="px-3"><PriorityChip v-if="showsInList(row.priority)" :priority="row.priority" /><span v-else class="text-surface-600">{{ priorityLabel(row.priority) }}</span></td>
              <td class="whitespace-nowrap px-3 tabular-nums text-surface-900">{{ waitingLabel(row.approved_at) }}</td>

              <td class="px-3 last:pr-6">
                <span v-if="canClaim" class="flex justify-end">
                  <ClaimSplitButton
                    :can-assign="isAdmin"
                    compact
                    :loading="claiming === row.id"
                    :request-ref="row.ref"
                    @assign="assigning = row"
                    @claim="claim(row)"
                  />
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Phones: cards, Claim asks first -->
      <ul v-else aria-label="Approved requests waiting for someone" class="m-0 flex list-none flex-col gap-1 p-0">
        <li v-for="row in shown" :key="row.id" class="relative flex flex-col gap-2 rounded-3xl px-3 py-3.5">
          <span class="flex items-center justify-between gap-2">
            <span class="font-mono text-xs font-medium text-surface-600" translate="no">{{ row.ref }}</span>
            <PriorityChip v-if="showsInList(row.priority)" :priority="row.priority" />
          </span>

          <router-link class="text-base font-semibold leading-snug text-surface-900 no-underline" :to="{ name: 'requests', params: { id: row.id } }">{{ row.title }}</router-link>
          <span class="text-sm text-surface-600"><span class="font-mono text-xs font-medium" translate="no">{{ stationsLabel(row) }}</span> · {{ row.org_name }} · {{ waitingLabel(row.approved_at) }}</span>

          <span v-if="canClaim" class="flex justify-end">
            <ClaimSplitButton
              :can-assign="isAdmin"
              :request-ref="row.ref"
              @assign="assigning = row"
              @claim="confirming = row"
            />
          </span>
        </li>
      </ul>
    </template>

    <!-- Phones: the same panel in a bottom sheet; the list behind follows at once -->
    <ModalSheet
      v-if="!mdAndUp"
      v-model="filterOpen"
      labelledby="qf-h"
      max-width="560"
      sheet
    >
      <div class="flex flex-col gap-4">
        <div class="flex items-center justify-between gap-3">
          <h2 id="qf-h" class="m-0 text-h2 text-surface-900">Search and filter</h2>

          <v-btn
            aria-label="Close"
            icon
            size="36"
            variant="text"
            @click="filterOpen = false"
          >
            <v-icon :icon="mdiClose" />
          </v-btn>
        </div>

        <QueueFilterPanel
          :filtered="filtered"
          :filters="filters"
          :groups="groups"
          :tables="false"
          @change="setFilters"
          @clear="clearFilters"
        />

        <v-btn block color="primary" @click="filterOpen = false">Show {{ shown.length }} {{ shown.length === 1 ? 'request' : 'requests' }}</v-btn>
      </div>
    </ModalSheet>

    <!-- Phones: claiming is one tap more, so a thumb can't take work by accident (mock-up W9) -->
    <ModalSheet v-model="confirmOpen" labelledby="cl-h" max-width="420">
      <div v-if="confirming" class="flex flex-col gap-3">
        <h2 id="cl-h" class="m-0 text-h2 text-surface-900">Claim this request?</h2>

        <div class="flex flex-col gap-0.5">
          <span class="font-mono text-xs font-medium text-surface-600" translate="no">{{ confirming.ref }}</span>
          <span class="text-base font-semibold text-surface-900">{{ confirming.title }}</span>
          <span class="text-sm text-surface-600"><span class="font-mono text-xs font-medium" translate="no">{{ stationsLabel(confirming) }}</span> · {{ confirming.org_name }}</span>
        </div>

        <p class="m-0 text-surface-700">It will show you as assigned. Admins are told, and the client sees your name.</p>

        <v-btn
          block
          color="primary"
          :loading="claiming === confirming.id"
          size="large"
          @click="claim(confirming)"
        >Claim request</v-btn>

        <v-btn
          block
          class="text-primary"
          size="large"
          variant="text"
          @click="confirming = null"
        >Not now</v-btn>
      </div>
    </ModalSheet>

    <AssignDialog
      v-if="assigning"
      v-model="assignOpen"
      :request="{ id: assigning.id, ref: assigning.ref, version: 1, status: 'approved', assigned_staff: [], stationCode: stationsLabel(assigning) }"
      @changed="load"
      @done="assigned"
    />

    <v-snackbar v-model="toast.show" location="bottom" :timeout="7000">
      {{ toast.text }}
      <template v-if="toast.to" #actions>
        <v-btn color="inverse-primary" :to="toast.to" variant="text" @click="toast.show = false">Open</v-btn>
      </template>
    </v-snackbar>
  </PageBody>
</template>

<script lang="ts" setup>
  import type { FilterGroup, QueueFilters } from './queue'
  import type { QueueItem, RequestDetail } from '@/api/models'
  import type { RouteLocationRaw } from 'vue-router'
  import { mdiClose, mdiInboxOutline, mdiMagnify } from '@mdi/js'
  import { storeToRefs } from 'pinia'
  import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { useDisplay } from 'vuetify'
  import { queueApi } from '@/api/operations'
  import { NetworkError } from '@/api/problem'
  import { isRequestUpdate, settled, useLive } from '@/app/composables/useLive'
  import { countryName } from '@/app/countries'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import ModalSheet from '@/components/ModalSheet.vue'
  import PageBody from '@/components/PageBody.vue'
  import PaneContent from '@/components/PaneContent.vue'
  import { useSessionStore } from '@/stores/session'
  import AssignDialog from './AssignDialog.vue'
  import ClaimSplitButton from './ClaimSplitButton.vue'
  import PriorityChip from './PriorityChip.vue'
  import { countBy, filterQueue, queueFiltersFrom, queueQueryFrom, waitingLabel } from './queue'
  import QueueFilterPanel from './QueueFilterPanel.vue'
  import { CATEGORIES, categoryLabel, PRIORITIES, priorityLabel, showsInList, stationsLabel } from './requests'
  import { claimRequest } from './staffingActions'

  // /queue (AFD §3, J4 step 4b, J5 steps 1 and 2; PRD REQ-7): approved requests nobody has taken,
  // oldest first. A technician claims; an admin claims or assigns. Staff only. A queue is short, so
  // the page loads it whole and filters here.
  const session = useSessionStore()
  const { roles } = storeToRefs(session)
  const route = useRoute()
  const router = useRouter()
  const { mdAndUp } = useDisplay()

  const items = ref<QueueItem[]>([])
  const loading = ref(true)
  const loadError = ref<string | null>(null)
  const claiming = ref<string | null>(null)
  const confirming = ref<QueueItem | null>(null)
  const assigning = ref<QueueItem | null>(null)
  const filterOpen = ref(false)
  const toast = reactive<{ show: boolean, text: string, to: RouteLocationRaw | null }>({ show: false, text: '', to: null })

  // Viewers read the queue and cannot take work (rule 5): no buttons for them, not disabled ones
  const canClaim = computed(() => roles.value.includes('technician') || roles.value.includes('admin'))
  const isAdmin = computed(() => roles.value.includes('admin'))

  const confirmOpen = computed({
    get: () => confirming.value !== null,
    set: value => {
      if (!value) {
        confirming.value = null
      }
    },
  })
  const assignOpen = computed({
    get: () => assigning.value !== null,
    set: value => {
      if (!value) {
        assigning.value = null
      }
    },
  })

  // --- Filters (in the URL) -----------------------------------------------------------------------

  const filters = computed(() => queueFiltersFrom(route.query))
  const shown = computed(() => filterQueue(items.value, filters.value))
  const activeCount = computed(() => Object.values(queueQueryFrom(filters.value)).filter(Boolean).length)
  const filtered = computed(() => activeCount.value > 0)

  function setFilters (patch: Partial<QueueFilters>): void {
    void router.replace({ query: { ...route.query, ...queueQueryFrom({ ...filters.value, ...patch }) } })
  }

  function clearFilters (): void {
    void router.replace({ query: {} })
  }

  const groups = computed<FilterGroup[]>(() => {
    // What each filter leaves when it alone is off, for its "Any"
    const anyOf = (field: FilterGroup['field']): number => filterQueue(items.value, { ...filters.value, [field]: null }).length
    const countries = countBy(items.value, filters.value, 'country')
    const priorities = countBy(items.value, filters.value, 'priority')
    const categories = countBy(items.value, filters.value, 'category')
    return [
      {
        field: 'priority' as const,
        label: 'Priority',
        any: anyOf('priority'),
        // Most urgent first; a fresh array, because toReversed needs iOS 16
        // eslint-disable-next-line unicorn/no-array-reverse
        options: [...PRIORITIES].reverse().filter(p => priorities.has(p.value)).map(p => ({ value: p.value, label: p.label, count: priorities.get(p.value) ?? 0 })),
      },
      {
        field: 'country' as const,
        label: 'Country',
        any: anyOf('country'),
        // Fresh array: sorting it in place is safe, and toSorted needs iOS 16
        // eslint-disable-next-line unicorn/no-array-sort
        options: [...countries].sort(([a], [b]) => countryName(a).localeCompare(countryName(b))).map(([value, count]) => ({ value, label: countryName(value), count })),
      },
      {
        field: 'category' as const,
        label: 'Category',
        any: anyOf('category'),
        options: CATEGORIES.filter(c => categories.has(c.value)).map(c => ({ value: c.value, label: c.label, count: categories.get(c.value) ?? 0 })),
      },
    ].filter(group => group.options.length > 0)
  })

  const subtitle = computed(() => {
    if (loading.value || loadError.value) {
      return undefined
    }
    const n = items.value.length
    return n === 0 ? 'Nothing is waiting.' : `${n} approved ${n === 1 ? 'request is' : 'requests are'} waiting for someone. Oldest first.`
  })

  function countriesOf (row: QueueItem): string {
    return [...new Set(row.stations.map(s => s.country))].join(', ') || '—'
  }

  // --- Loading ------------------------------------------------------------------------------------

  async function load (): Promise<void> {
    try {
      items.value = (await queueApi.list()).items
      loadError.value = null
    } catch (error) {
      if (items.value.length === 0) {
        loadError.value = error instanceof NetworkError
          ? 'This needs a connection. It will load when you have signal.'
          : 'We couldn’t load the queue. Reload the page to try again.'
      }
    } finally {
      loading.value = false
    }
  }

  // The queue changes under you (someone else claims): look again when the app comes back
  function refreshWhenVisible (): void {
    if (document.visibilityState === 'visible' && !loading.value) {
      void load()
    }
  }

  onMounted(() => {
    void load()
    document.addEventListener('visibilitychange', refreshWhenVisible)
  })

  onBeforeUnmount(() => document.removeEventListener('visibilitychange', refreshWhenVisible))

  // Someone claimed, assigned, approved or released a request: the queue follows (PRD NOT-5)
  const refresh = settled(() => {
    void load()
  })
  useLive(event => {
    if (event.entity === 'reconnected' || (isRequestUpdate(event) && event.kind !== 'comment')) {
      refresh()
    }
  })

  // --- Claim and assign ---------------------------------------------------------------------------

  function say (text: string, to: RouteLocationRaw | null = null): void {
    toast.text = text
    toast.to = to
    toast.show = true
  }

  async function claim (row: QueueItem): Promise<void> {
    if (claiming.value) {
      return
    }
    claiming.value = row.id
    const result = await claimRequest(row.id)
    claiming.value = null
    confirming.value = null
    if (result.ok) {
      items.value = items.value.filter(i => i.id !== row.id)
      say(`You claimed ${row.ref}. Admins have been told.`, { name: 'requests', params: { id: row.id } })
    } else {
      say(result.message)
      if (result.reload) {
        await load()
      }
    }
  }

  function assigned (request: RequestDetail): void {
    items.value = items.value.filter(i => i.id !== request.id)
    const names = request.assigned_staff.map(p => p.name).join(', ')
    say(`${request.ref} is assigned to ${names}.`, { name: 'requests', params: { id: request.id } })
  }
</script>
