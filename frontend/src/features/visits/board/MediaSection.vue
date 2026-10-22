<template>
  <section :aria-labelledby="headingId" class="flex min-w-0 flex-col gap-2">
    <div class="flex items-baseline justify-between gap-3">
      <h3 :id="headingId" class="m-0 text-sm font-semibold text-surface-900">{{ SECTION_LABEL[section] }}</h3>
      <span class="text-xs text-surface-600">{{ countText }}</span>
    </div>

    <!-- Config's files that are not photos or video: a row each -->
    <ul v-if="documents.length > 0" class="m-0 flex list-none flex-col overflow-hidden rounded-lg border border-surface-300 p-0">
      <li v-for="file in documents" :key="file.media_id" class="flex items-center border-b border-surface-200 last:border-b-0">
        <button
          class="flex min-h-14 min-w-0 flex-1 cursor-pointer items-center gap-3 border-0 bg-transparent px-3 py-2 text-left text-surface-900 hover:bg-surface-50"
          type="button"
          @click="emit('open', file)"
        >
          <span class="grid size-9 flex-none place-items-center rounded-lg bg-sticky-config text-[10px] font-bold text-on-sticky-config">{{ badge(file.filename) }}</span>

          <span class="flex min-w-0 flex-col">
            <span class="truncate font-mono text-[13px]" translate="no">{{ file.filename }}</span>
            <span class="text-xs text-surface-600">{{ sizeText(file.size_bytes) }}<template v-if="file.hidden"> · hidden from the client</template></span>
          </span>
        </button>

        <v-btn
          v-if="canEdit"
          :aria-label="`Remove ${file.filename}`"
          class="mr-1"
          icon
          size="small"
          variant="text"
          @click="remove(file)"
        ><v-icon :icon="mdiDeleteOutline" size="18" /></v-btn>
      </li>
    </ul>

    <ul v-if="pictures.length > 0 || pendingHere.length > 0 || canEdit" class="m-0 grid list-none grid-cols-3 gap-2 p-0 sm:grid-cols-4">
      <MediaThumb
        v-for="file in pictures"
        :key="file.media_id"
        :can-caption="canEdit"
        :can-remove="canEdit"
        fluid
        :item="file"
        @caption="captioning = file"
        @hide="hide(file, $event)"
        @open="emit('open', file)"
        @remove="remove(file)"
      />

      <PendingThumb
        v-for="item in pendingHere"
        :key="item.key"
        class="w-full!"
        :item="item"
        @discard="emit('discard', item.key)"
        @retry="emit('retry', item.key)"
      />

      <li v-if="canEdit" class="aspect-4/3">
        <label
          class="flex size-full cursor-pointer flex-col items-center justify-center gap-0.5 rounded-lg border-[1.5px] border-dashed border-surface-300 px-2 text-center text-xs font-semibold text-primary hover:bg-surface-50 focus-within:outline-2 focus-within:outline-primary"
        >
          <v-icon :icon="mdiPlus" size="20" />
          {{ anyFile ? 'File, photo or video' : 'Photo or video' }}
          <input
            :accept="anyFile ? undefined : 'image/*,video/*'"
            class="sr-only"
            multiple
            type="file"
            @change="picked"
          >
        </label>
      </li>
    </ul>

    <p v-else class="m-0 text-xs text-surface-600">Nothing here.</p>

    <p v-if="problem" class="m-0 text-xs text-error" role="alert">{{ problem }}</p>

    <CaptionDialog
      v-model="captionOpen"
      :element-id="element.id"
      :item="captioning"
      :station-id="stationId"
      :visit-id="visitId"
      @done="emit('changed', $event)"
    />
  </section>
</template>

<script lang="ts" setup>
  import type { BoardElement, BoardMedia, ElementSection } from '@/api/models'
  import type { PendingMedia } from '@/app/composables/useVisitMedia'
  import { mdiDeleteOutline, mdiPlus } from '@mdi/js'
  import { computed, ref } from 'vue'
  import { boardApi } from '@/api/operations'
  import CaptionDialog from '../CaptionDialog.vue'
  import { inOrder, mediaFailure, SECTION_LABEL } from '../media'
  import { forgetMedia } from '../mediaLinks'
  import MediaThumb from '../MediaThumb.vue'
  import PendingThumb from '../PendingThumb.vue'
  import { badge, sizeText } from '../viewers/view'

  // One file section of an element: "Photos and video" for a Note or Recommendation, Before and
  // After for a Task or Config (W11-27). Files go up through the visit's queue, so a large video
  // keeps going after the sheet closes; a file opens in place in the sheet (W11-29).
  const props = defineProps<{
    visitId: string
    stationId: string
    element: BoardElement
    section: ElementSection
    canEdit: boolean
    /** Config takes any file; the others photos and video. */
    anyFile: boolean
    pending: PendingMedia[]
  }>()

  const emit = defineEmits<{
    open: [file: BoardMedia]
    add: [files: File[]]
    changed: [element: BoardElement]
    retry: [key: string]
    discard: [key: string]
  }>()

  const headingId = computed(() => `ms-${props.element.id}-${props.section}`)
  const files = computed(() => inOrder(props.element.media[props.section] ?? []))
  const pictures = computed(() => files.value.filter(f => f.kind === 'image' || f.kind === 'video'))
  const documents = computed(() => files.value.filter(f => f.kind === 'config'))
  const pendingHere = computed(() => props.pending.filter(p => p.section === props.section))
  const countText = computed(() => {
    const n = files.value.length
    const coming = pendingHere.value.length
    const have = `${n} ${n === 1 ? 'file' : 'files'}`
    return coming > 0 ? `${have}, ${coming} on the way` : have
  })

  const problem = ref<string | null>(null)
  const captioning = ref<BoardMedia | null>(null)
  const captionOpen = computed({
    get: () => captioning.value !== null,
    set: open => {
      if (!open) {
        captioning.value = null
      }
    },
  })

  function picked (event: Event): void {
    const input = event.target as HTMLInputElement
    const chosen = [...(input.files ?? [])]
    input.value = ''
    if (chosen.length > 0) {
      problem.value = null
      emit('add', chosen)
    }
  }

  async function hide (file: BoardMedia, hidden: boolean): Promise<void> {
    problem.value = null
    try {
      emit('changed', await boardApi.changeMedia(props.visitId, props.stationId, props.element.id, file.media_id, { hidden }))
    } catch (error) {
      problem.value = mediaFailure(error, 'We couldn’t change that. Try again in a moment.')
    }
  }

  async function remove (file: BoardMedia): Promise<void> {
    problem.value = null
    try {
      const element = await boardApi.removeMedia(props.visitId, props.stationId, props.element.id, file.media_id)
      forgetMedia(file.media_id)
      emit('changed', element)
    } catch (error) {
      problem.value = mediaFailure(error, 'We couldn’t remove that. Try again in a moment.')
    }
  }
</script>
