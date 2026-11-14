<template>
  <v-dialog
    v-model="open"
    :aria-labelledby="headingId"
    :fullscreen="!mdAndUp"
    :max-width="wide ? 720 : 560"
    persistent
    scrollable
    @keydown.esc="done"
  >
    <div class="flex max-h-[calc(100dvh-48px)] flex-col overflow-hidden bg-surface max-md:max-h-dvh max-md:min-h-dvh md:rounded-[14px]">
      <!-- Header band in the kind's tint -->
      <header class="flex flex-none flex-col gap-1.5 border-t-4 px-5 pb-4 pt-3 max-md:pt-[calc(12px+env(safe-area-inset-top))]" :class="[look.tint, look.edge]">
        <div class="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-[0.06em]" :class="look.accent">
          <v-icon :icon="look.icon" size="16" />
          {{ look.label }}
          <span v-if="kind === 'task' && bar.total > 0" class="normal-case tracking-normal">· {{ bar.done }} of {{ bar.total }}</span>
          <span class="flex-1" />

          <span v-if="kind === 'task' && saved?.complete" class="inline-flex items-center gap-1 text-[13px] font-semibold normal-case tracking-normal">
            <v-icon :icon="mdiCheckCircleOutline" size="16" />Complete
          </span>

          <v-btn
            aria-label="Close"
            class="-my-2 -mr-2 text-surface-900"
            icon
            size="small"
            variant="text"
            @click="done"
          ><v-icon :icon="mdiClose" /></v-btn>
        </div>

        <h2 :id="headingId" class="font-heading m-0 text-[22px] font-semibold leading-tight text-surface-900">{{ draft.title.trim() || `New ${look.label.toLowerCase()}` }}</h2>
        <span class="text-xs text-surface-700">{{ byLine }}</span>
      </header>

      <!-- A file opened from the sheet: shown here, never in a new tab -->
      <FileViewer
        v-if="viewing && saved"
        v-model:file="viewing.file"
        :back-label="saved.title"
        :files="viewing.files"
        :zone="zone"
        @back="viewing = null"
      />

      <template v-else>
        <div class="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto overscroll-contain px-5 pb-5 pt-4">
          <FeedbackBanner v-if="deleted" type="info">This was deleted. Nothing you change here will be saved.</FeedbackBanner>

          <template v-else-if="conflict">
            <FeedbackBanner type="error">This was changed on another device. Here is the saved copy. What you typed is kept below so you can copy it.</FeedbackBanner>

            <div class="rounded-lg bg-surface-50 px-3.5 py-2.5 text-sm">
              <p class="m-0 text-xs font-semibold text-surface-700">Your version</p>
              <p class="m-0 font-medium text-surface-900">{{ conflict.title }}</p>
              <p v-if="conflict.description" class="m-0 whitespace-pre-line text-surface-700">{{ conflict.description }}</p>
            </div>

            <v-btn class="self-start" variant="outlined" @click="conflict = null">Edit the saved copy</v-btn>
          </template>

          <FeedbackBanner v-else-if="readOnlyReason" type="info">{{ readOnlyReason }}</FeedbackBanner>
          <FeedbackBanner v-if="problem" type="error">{{ problem }}</FeedbackBanner>

          <!-- Title and description -->
          <template v-if="editable">
            <FormField :id="`${headingId}-title`" label="Title">
              <v-text-field
                :id="`${headingId}-title`"
                v-model="draft.title"
                autocomplete="off"
                :counter="MAX_TITLE"
                :error-messages="titleError ?? undefined"
                :maxlength="MAX_TITLE"
                name="title"
                :placeholder="placeholder"
              />
            </FormField>

            <FormField :id="`${headingId}-desc`" label="Description (optional)">
              <template #aside>
                <span v-if="savedAt" class="inline-flex items-center gap-1 text-xs text-surface-600" role="status"><v-icon :icon="mdiCheck" size="14" />Saved · {{ savedAt }}</span>
                <span v-else-if="saving" class="text-xs text-surface-600" role="status">Saving…</span>
              </template>

              <v-textarea
                :id="`${headingId}-desc`"
                v-model="draft.description"
                auto-grow
                :maxlength="MAX_DESCRIPTION"
                name="description"
                rows="2"
              />
            </FormField>
          </template>

          <p v-else-if="saved?.description" class="m-0 whitespace-pre-line text-sm text-surface-900">{{ saved.description }}</p>

          <!-- A recommendation's priority -->
          <div v-if="kind === 'recommendation'" class="flex flex-col gap-2">
            <span :id="`${headingId}-prio`" class="text-label text-surface-900">Priority</span>

            <v-btn-toggle
              v-if="editable"
              v-model="draft.priority"
              :aria-labelledby="`${headingId}-prio`"
              class="self-start"
              color="primary"
              density="comfortable"
              divided
              mandatory
              variant="outlined"
            >
              <v-btn v-for="(label, value) in PRIORITY_LABEL" :key="value" :value="value">{{ label }}</v-btn>
            </v-btn-toggle>

            <span v-else class="text-sm text-surface-900">{{ PRIORITY_LABEL[saved?.priority ?? 'medium'] }}</span>
          </div>

          <!-- A task's checklist -->
          <section v-if="kind === 'task'" :aria-labelledby="`${headingId}-items`" class="flex flex-col gap-1">
            <div class="flex items-baseline justify-between">
              <h3 :id="`${headingId}-items`" class="m-0 text-sm font-semibold text-surface-900">Checklist</h3>
              <span class="text-xs text-surface-600">{{ bar.done }} of {{ bar.total }} done</span>
            </div>

            <ul v-if="draft.items.length > 0" class="m-0 flex list-none flex-col p-0">
              <li v-for="(item, i) in draft.items" :key="item.id" class="flex min-h-12 items-center gap-1 border-b border-surface-200 last:border-b-0">
                <v-checkbox-btn
                  v-model="item.done"
                  :aria-label="item.text"
                  :color="look.accent.replace('text-', '')"
                  :disabled="!editable"
                />

                <span class="flex min-w-0 flex-1 flex-col py-1.5">
                  <span class="text-sm" :class="item.done ? 'text-surface-700' : 'text-surface-900'">{{ item.text }}</span>
                  <span v-if="doneLine(item.id)" class="text-xs text-surface-600">{{ doneLine(item.id) }}</span>
                </span>

                <template v-if="editable">
                  <v-btn
                    :aria-label="`Move ${item.text} up`"
                    :disabled="i === 0"
                    icon
                    size="small"
                    variant="text"
                    @click="move(i, -1)"
                  ><v-icon :icon="mdiChevronUp" /></v-btn>

                  <v-btn
                    :aria-label="`Move ${item.text} down`"
                    :disabled="i === draft.items.length - 1"
                    icon
                    size="small"
                    variant="text"
                    @click="move(i, 1)"
                  ><v-icon :icon="mdiChevronDown" /></v-btn>

                  <v-btn
                    :aria-label="`Remove ${item.text}`"
                    icon
                    size="small"
                    variant="text"
                    @click="removeItem(i)"
                  ><v-icon :icon="mdiClose" size="18" /></v-btn>
                </template>
              </li>
            </ul>

            <p v-else class="m-0 py-1 text-sm text-surface-600">No items yet. Add what needs doing.</p>

            <form v-if="editable && draft.items.length < MAX_ITEMS" class="mt-1 flex items-start gap-2" @submit.prevent="addItem">
              <v-text-field
                v-model="newItem"
                aria-label="New item"
                autocomplete="off"
                class="flex-1"
                density="compact"
                hide-details
                :maxlength="MAX_ITEM"
                placeholder="Add an item…"
              />

              <v-btn
                class="mt-0.5"
                color="primary"
                :disabled="!newItem.trim()"
                type="submit"
                variant="tonal"
              >Add item</v-btn>
            </form>
          </section>

          <!-- Files: one section, or Before and After side by side -->
          <div v-if="saved" class="grid gap-4" :class="sections.length > 1 && mdAndUp ? 'grid-cols-2' : 'grid-cols-1'">
            <MediaSection
              v-for="section in sections"
              :key="section"
              :any-file="look.anyFile"
              :can-edit="editable"
              :element="saved"
              :pending="pending"
              :section="section"
              :station-id="stationId"
              :visit-id="visit.id"
              @add="addFiles(section, $event)"
              @changed="adopt"
              @discard="queue?.discard($event)"
              @open="openFile(section, $event)"
              @retry="queue?.retry($event)"
            />
          </div>

          <p v-else-if="editable" class="m-0 text-sm text-surface-600">Give it a title, then add photos{{ look.anyFile ? ' and files' : '' }}.</p>

          <!-- Config: the versions made from it, and the next one when its After files changed -->
          <template v-if="kind === 'config' && saved">
            <ul v-if="saved.config_versions.length > 0" aria-label="Configuration versions made from this" class="m-0 flex list-none flex-col gap-1.5 p-0">
              <li v-for="made in saved.config_versions" :key="made.id" class="flex items-center gap-2 rounded-lg bg-primary-100 px-3 py-2 text-sm text-primary-700 dark:bg-primary-800 dark:text-primary-100">
                <v-icon :icon="mdiCheck" size="16" />
                <span>The After files are <router-link class="font-semibold text-inherit" :to="{ name: 'stations', params: { id: stationId }, query: { tab: 'configurations' } }">configuration version {{ made.version }}</router-link> of {{ station?.station_name }}.</span>
              </li>
            </ul>

            <div v-if="visit.status === 'ended' && saved.version_due && editable" class="flex flex-wrap items-center gap-3">
              <v-btn color="primary" :loading="versioning" variant="tonal" @click="saveVersion">Save as a new configuration version</v-btn>
              <span class="text-xs text-surface-600">The After files changed since the last version.</span>
            </div>
          </template>

          <p v-if="kind === 'config' && editable && visit.status !== 'ended'" class="m-0 flex items-start gap-2 rounded-lg bg-surface-50 px-3 py-2.5 text-[13px] text-surface-700">
            <v-icon class="mt-px text-primary" :icon="mdiInformationOutline" size="16" />
            When the visit ends, the After files become the station’s next configuration version. Changing them later adds another version; a version never changes.
          </p>

          <!-- Recommendation: a request made from it (W11-38) -->
          <section v-if="kind === 'recommendation' && saved && !isClient" :aria-labelledby="`${headingId}-follow`" class="flex flex-col gap-2">
            <h3 :id="`${headingId}-follow`" class="m-0 text-sm font-semibold text-surface-900">Follow-up</h3>

            <p v-if="saved.request_ref" class="m-0 text-sm">
              <router-link class="font-mono font-semibold text-primary" :to="{ name: 'requests', params: { id: saved.request_ref.id } }" translate="no">Request {{ saved.request_ref.ref }}</router-link>
              <span class="text-surface-600"> was made from this.</span>
            </p>

            <template v-else-if="editable">
              <form v-if="requesting" class="flex flex-col gap-2" @submit.prevent="makeRequest">
                <v-select
                  v-model="category"
                  :items="categoryItems"
                  label="What kind of work"
                  name="category"
                />

                <p class="m-0 text-xs text-surface-600">{{ requestHint }}</p>

                <div class="flex gap-2">
                  <v-btn color="primary" :loading="makingRequest" type="submit">Make the request</v-btn>
                  <v-btn variant="text" @click="requesting = false">Cancel</v-btn>
                </div>
              </form>

              <v-btn
                v-else
                class="self-start"
                color="primary"
                :prepend-icon="mdiPlus"
                variant="tonal"
                @click="requesting = true"
              >Create a request from this</v-btn>
            </template>
          </section>

          <!-- Sharing -->
          <div v-if="!isClient" class="flex items-start gap-3 border-t border-surface-200 pt-3">
            <v-switch
              :id="`${headingId}-share`"
              v-model="draft.shared"
              class="flex-none"
              color="primary"
              :disabled="!editable"
              hide-details
              inset
            />

            <label class="min-w-0 pt-1.5" :for="`${headingId}-share`">
              <span class="block font-medium text-surface-900">Share with client</span>
              <span class="block text-xs text-surface-600">{{ shareHint }}</span>
            </label>
          </div>
        </div>

        <!-- Footer -->
        <footer class="flex flex-none items-center gap-2 border-t border-surface-200 px-4 py-3 max-md:pb-[calc(12px+env(safe-area-inset-bottom))]">
          <template v-if="confirmDelete">
            <span class="flex-1 text-sm text-surface-900">Delete this {{ look.label.toLowerCase() }}{{ fileCount > 0 ? ' and its files' : '' }}?</span>
            <v-btn variant="text" @click="confirmDelete = false">Keep it</v-btn>
            <v-btn color="error" :loading="removing" @click="removeElement">Delete</v-btn>
          </template>

          <template v-else>
            <v-btn
              v-if="saved && editable"
              class="text-surface-700"
              :prepend-icon="mdiDeleteOutline"
              variant="text"
              @click="confirmDelete = true"
            >Delete</v-btn>

            <span class="flex-1" />
            <v-btn color="primary" :loading="closing" @click="done">Done</v-btn>
          </template>
        </footer>
      </template>
    </div>
  </v-dialog>
</template>

<script lang="ts" setup>
  import type { Draft } from '../board'
  import type { BoardElement, BoardMedia, ElementKind, ElementSection, VisitOut } from '@/api/models'
  import type { PendingMedia } from '@/app/composables/useVisitMedia'
  import { mdiCheck, mdiCheckCircleOutline, mdiChevronDown, mdiChevronUp, mdiClose, mdiDeleteOutline, mdiInformationOutline, mdiPlus } from '@mdi/js'
  import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
  import { useDisplay } from 'vuetify'
  import { formatDateTime, formatListTime } from '@/app/format'
  import { newId } from '@/app/ids'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import FormField from '@/components/FormField.vue'
  import { CATEGORIES } from '@/features/requests/requests'
  import { useSessionStore } from '@/stores/session'
  import { boardFailure, changed, createBody, currentOf, draftOf, KIND, MAX_DESCRIPTION, MAX_ITEM, MAX_ITEMS, MAX_TITLE, moved, PRIORITY_LABEL, progress, putBody, sectionsOf, titleProblem } from '../board'
  import { board } from '../local/gateway'
  import { boardQueue, onElementSaved } from '../uploadQueues'
  import FileViewer from '../viewers/FileViewer.vue'
  import MediaSection from './MediaSection.vue'

  // An element of a station's board, opened (DBD 1.8 "Element sheet"; the approved Stitch sheets).
  // Text saves as it is typed, against the version this sheet started from (W11-26): a save made
  // elsewhere first comes back as a conflict, shown with the saved copy, and nothing is merged
  // (ADR-18). A new element is made on the server once it has a title. A dialog from 768 px; the
  // whole screen on a phone.
  const props = defineProps<{
    visit: VisitOut
    stationId: string
    /** The element opened, or null with `newKind` for one being added. */
    element: BoardElement | null
    newKind?: ElementKind | null
    isClient: boolean
    me?: string | null
  }>()

  const emit = defineEmits<{ saved: [element: BoardElement], deleted: [id: string] }>()
  const open = defineModel<boolean>({ required: true })

  const { mdAndUp } = useDisplay()
  const saved = ref<BoardElement | null>(props.element)
  const kind = computed<ElementKind>(() => saved.value?.kind ?? props.newKind ?? 'note')
  const look = computed(() => KIND[kind.value])
  const sections = computed(() => sectionsOf(kind.value))
  const wide = computed(() => sections.value.length > 1)
  const headingId = computed(() => `el-${saved.value?.id ?? 'new'}`)
  const station = computed(() => props.visit.stations.find(s => s.station_id === props.stationId))
  const zone = computed(() => station.value?.time_zone ?? null)
  const placeholder = computed(() => ({
    note: 'For example, water inside the enclosure…',
    task: 'For example, replace the RH sensor…',
    recommendation: 'For example, replace the guy wires next quarter…',
    config: 'For example, logger program 4.2…',
  })[kind.value])

  const draft = reactive<Draft>(blankDraft())
  const newItem = ref('')
  const saving = ref(false)
  const savedAt = ref<string | null>(null)
  const problem = ref<string | null>(null)
  const conflict = ref<Draft | null>(null)
  const deleted = ref(false)
  const confirmDelete = ref(false)
  const removing = ref(false)
  const closing = ref(false)
  const viewing = ref<{ file: BoardMedia, files: BoardMedia[] } | null>(null)
  const versioning = ref(false)
  const requesting = ref(false)
  const makingRequest = ref(false)
  const category = ref<(typeof CATEGORIES)[number]['value']>('inspection')
  const categoryItems = CATEGORIES.map(c => ({ title: c.label, value: c.value }))
  const requestId = newId()
  const session = useSessionStore()
  const requestHint = computed(() => session.hasAnyRole(['admin'])
    ? 'It starts Approved, for this station, with the title and description above. It needs a connection.'
    : 'It starts Submitted for an admin to approve, for this station, with the title and description above. It needs a connection.')
  const id = ref<string>(props.element?.id ?? newId())

  const editable = computed(() => {
    if (props.isClient || deleted.value) {
      return false
    }
    return saved.value ? saved.value.can_edit : true
  })
  const readOnlyReason = computed(() => {
    if (props.isClient || !saved.value || saved.value.can_edit) {
      return null
    }
    const status = props.visit.status
    if (status !== 'started' && status !== 'ended') {
      return null
    }
    return `Only ${saved.value.created_by.name} or the station’s owner can change this.`
  })
  const titleError = computed(() => saved.value || draft.title ? titleProblem(draft.title) : null)
  const bar = computed(() => progress(draft.items))
  const fileCount = computed(() => saved.value ? Object.values(saved.value.media).flat().length : 0)
  const queue = computed(() => saved.value ? boardQueue(props.visit) : null)
  const pending = computed<PendingMedia[]>(() => saved.value && queue.value ? queue.value.forElement(saved.value.id) : [])
  const byLine = computed(() => {
    const who = saved.value?.created_by.name ?? 'You'
    const where = station.value?.station_name ?? ''
    const when = saved.value ? formatDateTime(saved.value.created_at, zone.value) : 'not saved yet'
    return [who, where, when].filter(Boolean).join(' · ')
  })
  const shareHint = computed(() => {
    const kinds = { note: 'notes', task: 'tasks', recommendation: 'recommendations', config: 'configuration files' }[kind.value]
    const usual = look.value.sharedByDefault ? 'On' : 'Off'
    return `${usual} for ${kinds} unless you change it. Shared ones are shown to the client when the visit ends.`
  })

  function blankDraft (): Draft {
    return props.element
      ? draftOf(props.element)
      : { title: '', description: '', items: [], priority: props.newKind === 'recommendation' ? 'medium' : null, shared: KIND[props.newKind ?? 'note'].sharedByDefault }
  }

  function doneLine (itemId: string): string {
    const item = saved.value?.items.find(i => i.id === itemId)
    if (!item?.done || !item.done_at) {
      return ''
    }
    const who = item.done_by === saved.value?.created_by.id ? saved.value.created_by.name : (item.done_by === props.me ? 'You' : '')
    const at = formatDateTime(item.done_at, zone.value)
    return who ? `${who} · ${at}` : at
  }

  function adopt (element: BoardElement): void {
    saved.value = element
    id.value = element.id
    emit('saved', element)
  }

  // --- Saving: one request at a time, the newest draft wins --------------------------------------

  let timer: ReturnType<typeof setTimeout> | undefined
  let inFlight: Promise<void> | null = null
  let again = false

  async function save (): Promise<void> {
    clearTimeout(timer)
    if (inFlight) {
      again = true
      return inFlight
    }
    if (!editable.value || conflict.value || titleProblem(draft.title)) {
      return
    }
    if (saved.value && !changed(draft, saved.value)) {
      return
    }
    saving.value = true
    problem.value = null
    inFlight = (async () => {
      try {
        const element = saved.value
          ? await board.save(props.visit.id, props.stationId, saved.value.id, putBody(draft, saved.value.version))
          : await board.create(props.visit.id, props.stationId, createBody(id.value, kind.value, draft))
        adopt(element)
        savedAt.value = formatListTime(element.updated_at, zone.value)
      } catch (error) {
        const current = currentOf(error)
        if (current) {
          conflict.value = { ...draft, items: [...draft.items] }
          adopt(current)
          Object.assign(draft, draftOf(current))
        } else if ((error as { code?: string }).code === 'element_deleted') {
          deleted.value = true
        } else {
          problem.value = boardFailure(error, 'We couldn’t save that. It will be tried again when you change something.')
        }
      } finally {
        saving.value = false
        inFlight = null
      }
    })()
    await inFlight
    if (again) {
      again = false
      await save()
    }
  }

  // Typing waits for a pause; a tick, a priority or a switch saves at once
  watch(() => [draft.title, draft.description], () => {
    clearTimeout(timer)
    timer = setTimeout(save, 800)
  })
  watch(() => [draft.items.map(i => `${i.id}:${i.done}:${i.text}`).join('|'), draft.priority, draft.shared], () => {
    void save()
  })

  function addItem (): void {
    const text = newItem.value.trim()
    if (!text) {
      return
    }
    draft.items.push({ id: newId(), text: text.slice(0, MAX_ITEM), done: false })
    newItem.value = ''
  }

  function removeItem (index: number): void {
    draft.items.splice(index, 1)
  }

  function move (index: number, by: -1 | 1): void {
    draft.items = moved(draft.items, index, by)
  }

  async function addFiles (section: ElementSection, files: File[]): Promise<void> {
    if (!saved.value || !queue.value) {
      return
    }
    const refused = queue.value.add({ stationId: props.stationId, elementId: saved.value.id, section, anyFile: look.value.anyFile }, files)
    if (refused.length > 0) {
      problem.value = refused.length === 1
        ? `${refused[0]} isn’t a photo or video, so it was left out.`
        : `${refused.length} files weren’t photos or videos, so they were left out.`
    }
  }

  function openFile (section: ElementSection, file: BoardMedia): void {
    viewing.value = { file, files: saved.value?.media[section] ?? [file] }
  }

  /** After the end: the changed After files become the next configuration version (W11-37). */
  async function saveVersion (): Promise<void> {
    if (!saved.value) {
      return
    }
    versioning.value = true
    problem.value = null
    try {
      adopt(await board.saveConfigVersion(props.visit.id, props.stationId, saved.value.id))
    } catch (error) {
      problem.value = boardFailure(error, 'We couldn’t save the version. Try again in a moment.')
    } finally {
      versioning.value = false
    }
  }

  /** A request from the recommendation; the same request id again changes nothing (W11-38). */
  async function makeRequest (): Promise<void> {
    if (!saved.value) {
      return
    }
    await save()
    makingRequest.value = true
    problem.value = null
    try {
      adopt(await board.requestFrom(props.visit.id, props.stationId, saved.value.id, { id: requestId, category: category.value }))
      requesting.value = false
    } catch (error) {
      problem.value = boardFailure(error, 'We couldn’t make the request. Try again in a moment.')
    } finally {
      makingRequest.value = false
    }
  }

  async function removeElement (): Promise<void> {
    if (!saved.value) {
      return
    }
    removing.value = true
    problem.value = null
    try {
      await board.remove(props.visit.id, props.stationId, saved.value.id, saved.value.version)
      emit('deleted', saved.value.id)
      open.value = false
    } catch (error) {
      confirmDelete.value = false
      const current = currentOf(error)
      if (current) {
        adopt(current)
        Object.assign(draft, draftOf(current))
      }
      problem.value = boardFailure(error, 'We couldn’t delete it. Try again in a moment.')
    } finally {
      removing.value = false
    }
  }

  async function done (): Promise<void> {
    closing.value = true
    try {
      await save()
    } finally {
      closing.value = false
    }
    if (!problem.value || !saved.value) {
      open.value = false
    }
  }

  /** A newer copy of this element from elsewhere on the page: its files change, the typing stays. */
  function refreshed (element: BoardElement): void {
    if (saved.value && element.id === saved.value.id && element !== saved.value) {
      const typing = changed(draft, saved.value)
      saved.value = element
      if (!typing) {
        Object.assign(draft, draftOf(element))
      }
    }
  }

  // A file finished going up and landed on this element, here or from the board: show it
  watch(() => props.element, element => element && refreshed(element))
  onBeforeUnmount(onElementSaved(refreshed))
  onBeforeUnmount(() => clearTimeout(timer))
</script>
