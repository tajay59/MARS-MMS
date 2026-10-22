<template>
  <li class="relative flex w-33 flex-none flex-col overflow-hidden rounded-lg border bg-surface-50 max-md:w-28" :class="state === 'failed' ? 'border-error' : 'border-surface-200'">
    <div class="relative aspect-4/3 bg-surface-100">
      <button
        v-if="state === 'ready'"
        :aria-label="openLabel"
        class="group relative block size-full cursor-pointer border-0 bg-transparent p-0 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-primary"
        :disabled="opening"
        type="button"
        @click="open"
      >
        <img
          v-if="thumbnail && !broken"
          alt=""
          class="size-full object-cover"
          decoding="async"
          loading="lazy"
          :src="thumbnail"
          @error="broken = true"
        >

        <span v-else class="flex size-full items-center justify-center text-surface-500">
          <v-icon :icon="item.kind === 'video' ? icons.video : icons.photo" size="28" />
        </span>

        <span v-if="item.kind === 'video'" class="absolute inset-0 flex items-center justify-center">
          <span class="flex size-8 items-center justify-center rounded-full bg-black/55 text-white">
            <v-icon :icon="mdiPlay" size="20" />
          </span>
        </span>

        <span v-if="length" class="absolute bottom-1.5 right-1.5 rounded bg-black/65 px-1.5 text-[11px] font-semibold tabular-nums text-white">{{ length }}</span>
      </button>

      <div v-else-if="state === 'failed'" class="flex size-full items-center justify-center text-error">
        <v-icon :icon="mdiAlertCircleOutline" size="28" />
      </div>

      <div v-else class="flex size-full items-center justify-center text-surface-500">
        <v-icon :icon="item.kind === 'video' ? icons.video : icons.photo" size="28" />
      </div>

      <span v-if="item.hidden" class="absolute left-1.5 top-1.5 inline-flex items-center gap-1 rounded-md bg-surface px-1.5 py-0.5 text-[11px] font-semibold text-surface-900">
        <v-icon :icon="mdiEyeOffOutline" size="14" />
        Hidden from client
      </span>

      <v-menu v-if="canCaption || canRemove" location="bottom end">
        <template #activator="{ props: activator }">
          <v-btn
            v-bind="activator"
            :aria-label="`More for ${label}`"
            class="absolute! right-1 top-1 bg-black/45! text-white!"
            icon
            :size="28"
            variant="text"
          >
            <v-icon :icon="mdiDotsVertical" size="18" />
          </v-btn>
        </template>

        <v-list :aria-label="`Actions for ${label}`" density="compact" role="menu">
          <v-list-item
            v-if="canCaption"
            :prepend-icon="mdiPencilOutline"
            role="menuitem"
            title="Edit caption"
            @click="emit('caption')"
          />

          <v-list-item
            v-if="canCaption"
            :prepend-icon="item.hidden ? mdiEyeOutline : mdiEyeOffOutline"
            role="menuitem"
            :title="item.hidden ? 'Show to client' : 'Hide from client'"
            @click="emit('hide', !item.hidden)"
          />

          <v-list-item
            v-if="canRemove"
            :prepend-icon="mdiDeleteOutline"
            role="menuitem"
            title="Remove"
            @click="emit('remove')"
          />
        </v-list>
      </v-menu>
    </div>

    <div v-if="state === 'ready'" class="min-h-8.5 px-2 pb-2 pt-1.5 text-xs leading-snug text-surface-700">
      <span v-if="item.caption" class="line-clamp-2">{{ item.caption }}</span>
      <span v-else class="font-mono text-surface-600" translate="no">{{ item.filename }}</span>
    </div>

    <div v-else-if="state === 'failed'" class="flex flex-col gap-1.5 px-2 pb-2 pt-1.5 text-xs text-surface-700" role="alert">
      <span><b class="font-semibold text-surface-900">Couldn’t read <span class="font-mono" translate="no">{{ item.filename }}</span>.</b> {{ detail?.error ?? 'The file could not be processed.' }} Remove it and add the file again.</span>
      <span v-if="canRemove"><v-btn size="small" variant="outlined" @click="emit('remove')">Remove</v-btn></span>
    </div>

    <div v-else class="flex flex-col gap-0.5 px-2 pb-2 pt-1.5 text-xs text-surface-700" role="status">
      <span><b class="font-semibold text-surface-900">{{ state === 'loading' ? 'Checking' : 'Processing' }}</b> <span class="font-mono" translate="no">{{ item.filename }}</span></span>
      <span v-if="state === 'processing'" class="text-[11px] text-surface-600">Usually a minute or two</span>
    </div>
  </li>
</template>

<script lang="ts" setup>
  import type { MediaDetail, VisitMedia } from '@/api/models'
  import { mdiAlertCircleOutline, mdiDeleteOutline, mdiDotsVertical, mdiEyeOffOutline, mdiEyeOutline, mdiPencilOutline, mdiPlay } from '@mdi/js'
  import { computed, onBeforeUnmount, ref, watch } from 'vue'
  import { icons } from '@/app/theme/icons'
  import { clock, mediaDetail, onItsWay, openMedia } from './mediaLinks'

  // One photo or video on a station of a visit: its thumbnail from a ten-minute link, or where it
  // is in the checks (board "W11 screens" 1). The visit record holds the caption and who added it;
  // the media service knows whether the file is ready, so this asks it, and looks again every few
  // seconds while it is not. A click opens the picture in a new tab (the lightbox is W12).
  const props = defineProps<{
    item: VisitMedia
    canCaption: boolean
    canRemove: boolean
    /** Seconds between looks while a file is being processed. Tests set it small. */
    pollSeconds?: number
  }>()

  const emit = defineEmits<{
    caption: []
    hide: [hidden: boolean]
    remove: []
    problem: [text: string]
  }>()

  const detail = ref<MediaDetail | null>(null)
  const broken = ref(false)
  const opening = ref(false)
  let timer: ReturnType<typeof setTimeout> | undefined
  let gone = false

  const state = computed<'loading' | 'processing' | 'ready' | 'failed'>(() => {
    if (!detail.value) {
      return 'loading'
    }
    if (detail.value.status === 'ready') {
      return 'ready'
    }
    return onItsWay(detail.value.status) ? 'processing' : 'failed'
  })

  const thumbnail = computed(() => detail.value?.urls?.thumbnail ?? null)
  const length = computed(() => props.item.kind === 'video' ? clock(detail.value?.duration_s) : '')
  const label = computed(() => props.item.caption || props.item.filename)
  const openLabel = computed(() => `Open ${props.item.kind === 'video' ? 'video' : 'photo'}: ${label.value}`)

  async function look (): Promise<void> {
    clearTimeout(timer)
    try {
      const found = await mediaDetail(props.item.media_id)
      if (gone) {
        return
      }
      detail.value = found
      broken.value = false
    } catch {
      // A look that fails leaves what is shown; the next one may work
    }
    if (!gone && (!detail.value || onItsWay(detail.value.status))) {
      timer = setTimeout(look, (props.pollSeconds ?? 5) * 1000)
    }
  }

  async function open (): Promise<void> {
    opening.value = true
    try {
      await openMedia(props.item.media_id)
    } catch {
      emit('problem', 'We couldn’t open that file. Try again in a moment.')
    } finally {
      opening.value = false
    }
  }

  watch(() => props.item.media_id, () => {
    detail.value = null
    void look()
  }, { immediate: true })

  onBeforeUnmount(() => {
    gone = true
    clearTimeout(timer)
  })
</script>
