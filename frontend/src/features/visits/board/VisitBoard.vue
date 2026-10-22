<template>
  <section aria-labelledby="vb-h" class="flex flex-col gap-3">
    <div class="flex flex-wrap items-baseline justify-between gap-2">
      <h2 id="vb-h" class="m-0 text-h3 text-surface-900">Board</h2>

      <span v-if="!isClient" class="inline-flex items-center gap-1.5 text-xs text-surface-600">
        <v-icon class="text-primary" :icon="mdiInformationOutline" size="16" />
        Shared notes are shown to the client when the visit ends.
      </span>
    </div>

    <!-- Stations: a tab each when there are several -->
    <v-tabs
      v-if="visit.stations.length > 1"
      v-model="stationId"
      aria-label="Station"
      color="primary"
      density="comfortable"
      show-arrows
    >
      <v-tab v-for="station in visit.stations" :key="station.station_id" :value="station.station_id">
        <span class="flex flex-col items-start leading-tight">
          {{ station.station_name }}
          <small class="text-xs font-normal normal-case text-surface-600">{{ station.owner.id === me ? 'Owned by you' : `Owner ${station.owner.name}` }} · {{ boardCount(station) }}</small>
        </span>
      </v-tab>
    </v-tabs>

    <!-- Filters and Add -->
    <div class="flex flex-wrap items-center gap-2">
      <div aria-label="Show" class="-mx-1 flex min-w-0 flex-1 gap-1.5 overflow-x-auto px-1 pb-1 [scrollbar-width:none]" role="group">
        <button
          v-for="f in filters"
          :key="f"
          :aria-pressed="filter === f"
          class="inline-flex h-9 flex-none cursor-pointer items-center gap-1.5 rounded-full border-0 px-3 text-[13px] font-medium"
          :class="filter === f ? 'bg-primary-100 text-primary-700 dark:bg-primary-800 dark:text-primary-100' : 'bg-transparent text-surface-900 shadow-[inset_0_0_0_1px_rgb(var(--v-theme-surface-300))] hover:bg-surface-50'"
          type="button"
          @click="filter = f"
        >
          {{ FILTER_LABEL[f] }} <span class="text-xs tabular-nums opacity-80">{{ tally[f] }}</span>
        </button>
      </div>

      <v-menu v-if="canAdd && mdAndUp" location="bottom end">
        <template #activator="{ props: activator }">
          <v-btn v-bind="activator" color="primary" :prepend-icon="mdiPlus">Add</v-btn>
        </template>

        <v-list aria-label="Add to the board" class="w-85" role="menu">
          <v-list-item
            v-for="k in KINDS"
            :key="k"
            class="py-2"
            role="menuitem"
            @click="add(k)"
          >
            <template #prepend>
              <span class="mr-3 grid size-9 place-items-center rounded-lg border-t-[3px]" :class="[KIND[k].tint, KIND[k].accent, KIND[k].edge]">
                <v-icon :icon="KIND[k].icon" size="20" />
              </span>
            </template>

            <v-list-item-title class="font-semibold">{{ KIND[k].label }}</v-list-item-title>
            <v-list-item-subtitle class="text-xs! opacity-100! text-surface-600">{{ KIND[k].hint }}</v-list-item-subtitle>
          </v-list-item>
        </v-list>
      </v-menu>
    </div>

    <FeedbackBanner v-if="error" type="error">
      <p class="m-0">{{ error }}</p>
      <v-btn class="mt-2" size="small" variant="outlined" @click="load()">Try again</v-btn>
    </FeedbackBanner>

    <div v-else-if="loading" aria-label="Loading the board…" class="grid grid-cols-1 gap-3.5 sm:grid-cols-2 lg:grid-cols-3" role="status">
      <v-skeleton-loader
        v-for="n in 3"
        :key="n"
        class="rounded-card"
        height="170"
        type="image"
      />
    </div>

    <!-- Empty -->
    <div v-else-if="elements.length === 0" class="flex flex-col items-center gap-2 py-10 text-center">
      <span class="grid size-14 place-items-center rounded-2xl bg-surface-100 text-surface-600"><v-icon :icon="icons.note" size="28" /></span>
      <b class="text-base text-surface-900">{{ isClient ? 'Nothing was shared from this station' : 'Nothing recorded at this station yet' }}</b>
      <p v-if="!isClient" class="m-0 max-w-[38ch] text-sm text-surface-600">Add a note, a task, a recommendation or configuration files as you work.</p>
    </div>

    <p v-else-if="list.length === 0" class="m-0 py-6 text-center text-sm text-surface-600">No {{ FILTER_LABEL[filter].toLowerCase() }} at this station.</p>

    <ul v-else :aria-label="`Board of ${currentStation?.station_name ?? 'the station'}`" class="m-0 grid list-none grid-cols-1 items-start gap-3.5 p-0 sm:grid-cols-2 lg:grid-cols-3">
      <li v-for="element in list" :key="element.id">
        <StickyNote
          :element="element"
          :show-sharing="!isClient"
          :uploading="uploadingFor(element.id)"
          @open="openElement(element)"
        />
      </li>
    </ul>

    <!-- Phones: a floating Add, and the kinds in a sheet from the bottom -->
    <v-btn
      v-if="canAdd && !mdAndUp"
      class="fixed! bottom-[calc(88px+env(safe-area-inset-bottom))] right-4 z-10"
      color="primary"
      height="56"
      :prepend-icon="mdiPlus"
      rounded="lg"
      @click="sheet = true"
    >Add</v-btn>

    <v-bottom-sheet v-model="sheet" aria-labelledby="vb-add-h">
      <div class="overscroll-contain rounded-t-3xl bg-surface px-3 pb-[calc(24px+env(safe-area-inset-bottom))] pt-2.5">
        <span aria-hidden="true" class="mx-auto mb-2.5 block h-1 w-9 rounded-full bg-surface-300" />
        <h3 id="vb-add-h" class="font-heading m-0 mx-2 mb-2 text-lg font-semibold">Add to the board</h3>

        <button
          v-for="k in KINDS"
          :key="k"
          class="grid min-h-16 w-full cursor-pointer grid-cols-[44px_1fr] items-center gap-3 rounded-xl border-0 bg-transparent px-2 py-2.5 text-left text-surface-900 hover:bg-surface-50"
          type="button"
          @click="add(k)"
        >
          <span class="grid size-11 place-items-center rounded-lg border-t-[3px]" :class="[KIND[k].tint, KIND[k].accent, KIND[k].edge]"><v-icon :icon="KIND[k].icon" /></span>
          <span><b class="block text-[15px] font-semibold">{{ KIND[k].label }}</b><small class="block text-[13px] text-surface-600">{{ KIND[k].hint }}</small></span>
        </button>
      </div>
    </v-bottom-sheet>

    <ElementDialog
      v-if="sheetOpen && stationId"
      :key="opened?.id ?? `new-${newKind}`"
      v-model="sheetOpen"
      :element="opened"
      :is-client="isClient"
      :me="me"
      :new-kind="newKind"
      :station-id="stationId"
      :visit="visit"
      @deleted="forget"
      @saved="merge"
    />
  </section>
</template>

<script lang="ts" setup>
  import type { BoardFilter } from '../board'
  import type { BoardElement, ElementKind, VisitOut, VisitStation } from '@/api/models'
  import { mdiInformationOutline, mdiPlus } from '@mdi/js'
  import { computed, onBeforeUnmount, ref, watch } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { useDisplay } from 'vuetify'
  import { boardApi } from '@/api/operations'
  import { isVisitUpdate, settled, useLive } from '@/app/composables/useLive'
  import { icons } from '@/app/theme/icons'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import { boardFailure, counts, FILTER_LABEL, KIND, KINDS, shown, summaryText } from '../board'
  import { boardQueue, onElementSaved } from '../uploadQueues'
  import ElementDialog from './ElementDialog.vue'
  import StickyNote from './StickyNote.vue'

  // A station's board on the visit page (PRD VIS-5, VIS-7; DBD 1.8 "Board"; the approved Stitch
  // board): filter chips, Add, and the sticky notes, newest first. Staff see it from the start;
  // a client sees the shared elements once the visit has ended (the server decides both). Changes
  // made by others arrive through the live visit message and a quiet reload.
  const props = defineProps<{
    visit: VisitOut
    isClient: boolean
    me?: string | null
  }>()

  const emit = defineEmits<{ changed: [] }>()

  const { mdAndUp } = useDisplay()
  const filters: BoardFilter[] = ['all', 'note', 'task', 'recommendation', 'config']

  /** The person's own station first, else the first. */
  function firstStation (): string | null {
    return (props.visit.stations.find(s => s.owner.id === props.me) ?? props.visit.stations[0])?.station_id ?? null
  }

  const route = useRoute()
  const router = useRouter()

  /** The station and the filter are in the address (`?station=`, `?show=`): a reload or Back keeps them. */
  const stationId = computed<string | null>({
    get: () => {
      const wanted = route.query.station
      return typeof wanted === 'string' && props.visit.stations.some(s => s.station_id === wanted) ? wanted : firstStation()
    },
    set: value => void router.replace({ query: { ...route.query, station: value ?? undefined, show: undefined } }),
  })
  const filter = computed<BoardFilter>({
    get: () => {
      const wanted = route.query.show
      return typeof wanted === 'string' && (filters as string[]).includes(wanted) ? wanted as BoardFilter : 'all'
    },
    set: value => void router.replace({ query: { ...route.query, show: value === 'all' ? undefined : value } }),
  })
  const elements = ref<BoardElement[]>([])
  const canAdd = ref(false)
  const loading = ref(true)
  const error = ref<string | null>(null)
  const sheet = ref(false)
  const sheetOpen = ref(false)
  const opened = ref<BoardElement | null>(null)
  const newKind = ref<ElementKind | null>(null)

  const currentStation = computed(() => props.visit.stations.find(s => s.station_id === stationId.value))
  const tally = computed(() => counts(elements.value))
  const list = computed(() => shown(elements.value, filter.value))
  const queue = computed(() => props.isClient ? null : boardQueue(props.visit))

  function boardCount (station: VisitStation): string {
    const n = station.board.note + station.board.task + station.board.recommendation + station.board.config
    return n === 0 ? summaryText(station.board) : `${n} on the board`
  }

  function uploadingFor (elementId: string): number {
    return queue.value?.forElement(elementId).length ?? 0
  }

  let abort: AbortController | null = null

  async function load (quiet = false): Promise<void> {
    const sid = stationId.value
    if (!sid) {
      return
    }
    abort?.abort()
    const controller = new AbortController()
    abort = controller
    if (!quiet) {
      loading.value = true
      error.value = null
    }
    try {
      const page = await boardApi.list(props.visit.id, sid, controller.signal)
      if (controller.signal.aborted) {
        return
      }
      elements.value = page.items
      canAdd.value = page.can_add
      error.value = null
    } catch (error_) {
      if (!controller.signal.aborted && !quiet) {
        error.value = boardFailure(error_, 'We couldn’t load the board. Check your signal, then try again.')
      }
    } finally {
      if (abort === controller) {
        loading.value = false
      }
    }
  }

  function merge (element: BoardElement): void {
    if (element.station_id !== stationId.value) {
      return
    }
    const at = elements.value.findIndex(e => e.id === element.id)
    elements.value = at === -1
      ? [element, ...elements.value]
      : elements.value.map(e => e.id === element.id ? element : e)
    if (opened.value?.id === element.id) {
      opened.value = element
    }
    emit('changed')
  }

  function forget (id: string): void {
    elements.value = elements.value.filter(e => e.id !== id)
    emit('changed')
  }

  function add (kind: ElementKind): void {
    sheet.value = false
    opened.value = null
    newKind.value = kind
    sheetOpen.value = true
  }

  function openElement (element: BoardElement): void {
    newKind.value = null
    opened.value = element
    sheetOpen.value = true
  }

  watch([stationId, () => props.visit.id], () => void load(), { immediate: true })
  // The visit itself changed (it ended, an owner changed): its end made versions and shared files
  watch(() => props.visit.version, () => void load(true))

  const refresh = settled(() => void load(true))
  useLive(event => {
    if (isVisitUpdate(event) && event.id === props.visit.id && !sheetOpen.value) {
      refresh()
    }
  })

  onBeforeUnmount(onElementSaved(merge))
  onBeforeUnmount(() => abort?.abort())
</script>
