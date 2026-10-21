<template>
  <PageBody :subtitle="subtitle" title="Queue" wide>
    <!-- The pane: search, then country, priority and category with how many each leaves -->
    <PaneContent pin>
      <div class="flex flex-col gap-4 px-3">
        <v-text-field
          aria-label="Search the queue by reference, title or station"
          autocomplete="off"
          class="px-1"
          clearable
          hide-details
          :model-value="filters.q"
          name="q"
          placeholder="Search reference, title or station"
          :prepend-inner-icon="mdiMagnify"
          spellcheck="false"
          type="search"
          @update:model-value="setFilters({ q: $event ?? '' })"
        />

        <div
          v-for="group in groups"
          :key="group.field"
          :aria-labelledby="`q-${group.field}`"
          class="flex flex-col gap-2 px-1"
          role="group"
        >
          <h3 :id="`q-${group.field}`" class="m-0 text-xs font-semibold uppercase tracking-wide text-surface-600">{{ group.label }}</h3>

          <div class="flex flex-wrap gap-1.5">
            <button
              :aria-pressed="filters[group.field] === null"
              class="inline-flex h-8 items-center gap-1.5 rounded-lg border px-3 text-sm"
              :class="chip(filters[group.field] === null)"
              type="button"
              @click="setFilters({ [group.field]: null })"
            >Any</button>

            <button
              v-for="option in group.options"
              :key="option.value"
              :aria-pressed="filters[group.field] === option.value"
              class="inline-flex h-8 items-center gap-1.5 rounded-lg border px-3 text-sm"
              :class="chip(filters[group.field] === option.value)"
              type="button"
              @click="setFilters({ [group.field]: filters[group.field] === option.value ? null : option.value })"
            >{{ option.label }}<span class="tabular-nums font-semibold">{{ option.count }}</span></button>
          </div>
        </div>

        <button
          v-if="filtered"
          class="self-start rounded-md px-2 py-1.5 text-sm font-medium text-primary hover:bg-surface-100"
          type="button"
          @click="clearFilters"
        >Clear filters</button>
      </div>
    </PaneContent>

    <FeedbackBanner v-if="loadError" type="error">{{ loadError }}</FeedbackBanner>

    <div v-else-if="loading" aria-label="Loading the queue…" class="flex flex-col gap-2" role="status">
      <v-skeleton-loader v-for="n in 4" :key="n" type="list-item-two-line" />
    </div>

    <template v-else>
      <div v-if="items.length === 0" class="flex flex-col items-center gap-2 py-12 text-center text-surface-600">
        <v-icon :icon="mdiInboxOutline" size="48" />
        <p class="m-0 text-h3 text-surface-900">The queue is empty</p>
        <p class="m-0">Approved requests that nobody has taken show up here.</p>
      </div>

      <p v-else-if="shown.length === 0" class="m-0 py-8 text-center text-surface-600">
        Nothing in the queue matches.
        <button class="font-medium text-primary hover:underline" type="button" @click="clearFilters">Clear filters</button>
      </p>

      <!-- From 768 px: a table, oldest approval first -->
      <div v-else-if="mdAndUp" class="overflow-x-auto">
        <table class="w-full border-collapse text-sm">
          <caption class="sr-only">Approved requests waiting for someone, oldest first</caption>

          <thead>
            <tr class="bg-surface-100 text-left">
              <th class="whitespace-nowrap px-3 py-3 text-xs font-medium text-surface-700" scope="col">Reference</th>
              <th class="whitespace-nowrap px-3 py-3 text-xs font-medium text-surface-700" scope="col">Request</th>
              <th class="whitespace-nowrap px-3 py-3 text-xs font-medium text-surface-700" scope="col">Organization</th>
              <th class="whitespace-nowrap px-3 py-3 text-xs font-medium text-surface-700" scope="col">Country</th>
              <th class="whitespace-nowrap px-3 py-3 text-xs font-medium text-surface-700" scope="col">Priority</th>
              <th class="whitespace-nowrap px-3 py-3 text-xs font-medium text-surface-700" scope="col">Waiting</th>
              <th class="px-3 py-3 text-right text-xs font-medium text-surface-700" scope="col"><span class="sr-only">Actions</span></th>
            </tr>
          </thead>

          <tbody>
            <tr v-for="row in shown" :key="row.id" class="h-15 border-t border-surface-200">
              <td class="whitespace-nowrap px-3 font-mono text-xs font-medium text-surface-600" translate="no">{{ row.ref }}</td>

              <td class="max-w-80 px-3">
                <router-link class="block truncate font-medium text-surface-900 no-underline hover:underline" :title="row.title" :to="{ name: 'requests', params: { id: row.id } }">{{ row.title }}</router-link>
                <span class="block truncate font-mono text-xs font-medium text-surface-600" translate="no">{{ stationsLabel(row) }} · {{ categoryLabel(row.category) }}</span>
              </td>

              <td class="max-w-40 truncate px-3 text-surface-900" :title="row.org_name ?? undefined">{{ row.org_name ?? '—' }}</td>
              <td class="whitespace-nowrap px-3 text-surface-900">{{ countriesOf(row) }}</td>
              <td class="px-3"><PriorityChip v-if="showsInList(row.priority)" :priority="row.priority" /><span v-else class="text-surface-600">{{ priorityLabel(row.priority) }}</span></td>
              <td class="whitespace-nowrap px-3 tabular-nums text-surface-900">{{ waitingLabel(row.approved_at) }}</td>

              <td class="px-3">
                <span v-if="canClaim" class="flex justify-end gap-2">
                  <v-btn
                    v-if="isAdmin"
                    color="primary"
                    size="small"
                    variant="outlined"
                    @click="assigning = row"
                  >Assign</v-btn>

                  <v-btn
                    :aria-label="`Claim ${row.ref}`"
                    color="primary"
                    :loading="claiming === row.id"
                    size="small"
                    @click="claim(row)"
                  >Claim</v-btn>
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

          <span v-if="canClaim" class="flex justify-end gap-2">
            <v-btn
              v-if="isAdmin"
              color="primary"
              size="small"
              variant="outlined"
              @click="assigning = row"
            >Assign</v-btn>

            <v-btn :aria-label="`Claim ${row.ref}`" color="primary" size="small" @click="confirming = row">Claim</v-btn>
          </span>
        </li>
      </ul>
    </template>

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
  import type { QueueFilters } from './queue'
  import type { QueueItem, RequestDetail } from '@/api/models'
  import type { RouteLocationRaw } from 'vue-router'
  import { mdiInboxOutline, mdiMagnify } from '@mdi/js'
  import { storeToRefs } from 'pinia'
  import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { useDisplay } from 'vuetify'
  import { queueApi } from '@/api/operations'
  import { NetworkError } from '@/api/problem'
  import { countryName } from '@/app/countries'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import ModalSheet from '@/components/ModalSheet.vue'
  import PageBody from '@/components/PageBody.vue'
  import PaneContent from '@/components/PaneContent.vue'
  import { useSessionStore } from '@/stores/session'
  import AssignDialog from './AssignDialog.vue'
  import PriorityChip from './PriorityChip.vue'
  import { countBy, filterQueue, queueFiltersFrom, queueQueryFrom, waitingLabel } from './queue'
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
  const filtered = computed(() => Object.values(queueQueryFrom(filters.value)).some(Boolean))

  function setFilters (patch: Partial<QueueFilters>): void {
    void router.replace({ query: { ...route.query, ...queueQueryFrom({ ...filters.value, ...patch }) } })
  }

  function clearFilters (): void {
    void router.replace({ query: {} })
  }

  function chip (on: boolean): string {
    return on
      ? 'border-transparent bg-primary-100 font-medium text-primary-800 dark:bg-primary-800 dark:text-primary-100'
      : 'border-surface-300 text-surface-900'
  }

  const groups = computed(() => {
    const countries = countBy(items.value, filters.value, 'country')
    const priorities = countBy(items.value, filters.value, 'priority')
    const categories = countBy(items.value, filters.value, 'category')
    return [
      {
        field: 'country' as const,
        label: 'Country',
        // Fresh array: sorting it in place is safe, and toSorted needs iOS 16
        // eslint-disable-next-line unicorn/no-array-sort
        options: [...countries].sort(([a], [b]) => countryName(a).localeCompare(countryName(b))).map(([value, count]) => ({ value, label: countryName(value), count })),
      },
      {
        field: 'priority' as const,
        label: 'Priority',
        // Most urgent first; a fresh array, because toReversed needs iOS 16
        // eslint-disable-next-line unicorn/no-array-reverse
        options: [...PRIORITIES].reverse().filter(p => priorities.has(p.value)).map(p => ({ value: p.value, label: p.label, count: priorities.get(p.value) ?? 0 })),
      },
      {
        field: 'category' as const,
        label: 'Category',
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
