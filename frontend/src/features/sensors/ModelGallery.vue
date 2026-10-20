<template>
  <section aria-labelledby="gal-h">
    <div class="mb-2.5 flex flex-wrap items-center justify-between gap-2">
      <div class="flex items-center gap-2.5">
        <h2 id="gal-h" class="m-0 text-h3 text-surface-900">Photos</h2>
        <span v-if="ready.length > 0" class="rounded bg-surface-100 px-2 py-0.5 text-xs text-surface-700">{{ ready.length }} {{ ready.length === 1 ? 'photo' : 'photos' }}</span>
        <span v-if="checking > 0" class="text-xs text-surface-600" role="status">{{ checking }} being checked…</span>
      </div>

      <div class="flex items-center gap-2">
        <div v-if="ready.length > 1" class="inline-flex shrink-0 items-center rounded-full bg-surface-100 px-1">
          <v-btn
            aria-label="Previous photo"
            icon
            size="32"
            variant="text"
            @click="step(-1)"
          >
            <v-icon :icon="mdiChevronLeft" size="20" />
          </v-btn>

          <span class="whitespace-nowrap px-1 text-xs tabular-nums text-surface-800">{{ index + 1 }} / {{ ready.length }}</span>

          <v-btn
            aria-label="Next photo"
            icon
            size="32"
            variant="text"
            @click="step(1)"
          >
            <v-icon :icon="mdiChevronRight" size="20" />
          </v-btn>
        </div>

        <v-btn
          v-if="canWrite && current"
          color="primary"
          :prepend-icon="mdiSwapHorizontal"
          variant="text"
          @click="startUpload(current)"
        >Replace</v-btn>

        <v-btn
          v-if="canWrite"
          color="primary"
          :prepend-icon="mdiImagePlusOutline"
          variant="tonal"
          @click="startUpload(null)"
        >Add a photo</v-btn>
      </div>
    </div>

    <FeedbackBanner v-if="error" type="error">{{ error }}</FeedbackBanner>

    <v-skeleton-loader v-else-if="docs === null" aria-label="Loading photos…" role="status" type="image" />

    <div
      v-else-if="ready.length === 0"
      class="flex h-36 flex-col items-center justify-center gap-1.5 rounded-card border-[1.5px] border-dashed border-surface-400 bg-surface-50 text-center"
    >
      <v-icon class="text-surface-500" :icon="icons.photo" size="28" />
      <p class="m-0 text-sm text-surface-700">{{ checking > 0 ? 'The photos are being checked.' : 'No photos of this model yet.' }}</p>
    </div>

    <div v-else class="relative overflow-hidden rounded-card bg-surface-100">
      <div
        ref="track"
        aria-label="Photos of this model"
        class="flex snap-x snap-mandatory overflow-x-auto scroll-smooth [-ms-overflow-style:none] [scrollbar-width:none] motion-reduce:scroll-auto [&::-webkit-scrollbar]:hidden"
        role="group"
        @scroll.passive="onScroll"
      >
        <figure
          v-for="(doc, i) in ready"
          :key="doc.id"
          :aria-label="`Photo ${i + 1} of ${ready.length}`"
          class="relative m-0 h-56 w-full shrink-0 snap-center sm:h-72"
        >
          <ModelPhoto
            :alt="doc.title"
            class="size-full"
            :document-id="doc.id"
            :icon="icons.photo"
            :icon-size="40"
          />

          <figcaption class="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/60 to-transparent px-3 pb-3 pt-8 text-sm text-white">{{ doc.title }}</figcaption>
        </figure>
      </div>

      <template v-if="ready.length > 1">
        <v-btn
          aria-label="Previous photo"
          class="!absolute left-2 top-1/2 -translate-y-1/2 bg-black/50 text-white"
          icon
          size="36"
          variant="flat"
          @click="step(-1)"
        >
          <v-icon :icon="mdiChevronLeft" size="22" />
        </v-btn>

        <v-btn
          aria-label="Next photo"
          class="!absolute right-2 top-1/2 -translate-y-1/2 bg-black/50 text-white"
          icon
          size="36"
          variant="flat"
          @click="step(1)"
        >
          <v-icon :icon="mdiChevronRight" size="22" />
        </v-btn>
      </template>
    </div>

    <UploadDialog
      v-if="canWrite"
      v-model="uploading"
      photo
      :replaces="replacing"
      scope="model"
      :scope-id="model.id"
      :subject="`${model.manufacturer} ${model.model}`"
      @saved="onSaved"
    />
  </section>
</template>

<script lang="ts" setup>
  import type { DocumentOut, SensorModelOut } from '@/api/models'
  import { mdiChevronLeft, mdiChevronRight, mdiImagePlusOutline, mdiSwapHorizontal } from '@mdi/js'
  import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
  import { documentsApi } from '@/api/operations'
  import { ApiError, NetworkError } from '@/api/problem'
  import { icons } from '@/app/theme/icons'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import { docState, PHOTO_TYPE } from '@/features/stations/documents'
  import UploadDialog from '@/features/stations/UploadDialog.vue'
  import ModelPhoto from './ModelPhoto.vue'

  // A sensor model's photos (W6-12): a swipeable strip, one picture at a time, with the caption
  // over it. Photos are documents of the model with the type `photo`. Staff only.
  const props = defineProps<{
    model: SensorModelOut
    canWrite: boolean
    /** Changes when photos were added elsewhere (the model form), so this looks again. */
    refresh: number
  }>()

  const emit = defineEmits<{
    /** A photo was added or replaced, so the catalogue's cover pictures are out of date. */
    changed: []
  }>()

  const docs = ref<DocumentOut[] | null>(null)
  const error = ref<string | null>(null)
  const index = ref(0)
  const track = ref<HTMLElement | null>(null)
  const uploading = ref(false)
  const replacing = ref<DocumentOut | null>(null)

  // Oldest first: the first photo is the model's cover in the list
  const ready = computed(() => (docs.value ?? []).filter(d => docState(d) === 'ready').toSorted((a, b) => a.created_at.localeCompare(b.created_at)))
  const checking = computed(() => (docs.value ?? []).filter(d => docState(d) === 'checking').length)
  const current = computed(() => ready.value[index.value] ?? null)

  async function load (quiet = false): Promise<void> {
    if (!quiet) {
      error.value = null
    }
    const id = props.model.id
    try {
      const page = await documentsApi.list({ scope: 'model', scope_id: id, doc_type: PHOTO_TYPE, limit: 50 })
      if (id === props.model.id) {
        docs.value = page.items
        index.value = Math.min(index.value, Math.max(0, ready.value.length - 1))
        error.value = null
      }
    } catch (error_) {
      if (!quiet) {
        error.value = error_ instanceof NetworkError
          ? 'This needs a connection. It will load when you have signal.'
          : (error_ instanceof ApiError ? error_.detail : 'We couldn’t load the photos. Reload the page to try again.')
      }
    }
  }

  // Look again while media is still checking a file (five minutes at most)
  let timer: ReturnType<typeof setTimeout> | undefined
  let polls = 0
  function schedule (): void {
    clearTimeout(timer)
    if (checking.value === 0 || polls >= 75) {
      return
    }
    timer = setTimeout(async () => {
      polls++
      if (!document.hidden) {
        await load(true)
      }
      schedule()
    }, 4000)
  }

  watch(() => props.model.id, () => {
    docs.value = null
    index.value = 0
    polls = 0
    void load()
  }, { immediate: true })
  watch(() => props.refresh, () => {
    polls = 0
    void load(true)
  })
  watch(checking, () => {
    polls = 0
    schedule()
  })
  onBeforeUnmount(() => clearTimeout(timer))

  function step (by: number): void {
    const el = track.value
    if (el) {
      el.scrollBy({ left: by * el.clientWidth })
    }
  }

  function onScroll (): void {
    const el = track.value
    if (el && el.clientWidth > 0) {
      index.value = Math.round(el.scrollLeft / el.clientWidth)
    }
  }

  function startUpload (replaces: DocumentOut | null): void {
    replacing.value = replaces
    uploading.value = true
  }

  async function onSaved (): Promise<void> {
    await load(true)
    emit('changed')
    await nextTick()
    polls = 0
    schedule()
  }
</script>
