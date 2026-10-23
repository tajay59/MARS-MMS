<template>
  <!-- The title is the button, and its click area covers the whole card: the card's name is the
       title alone and the rest is read as text (WCAG 2.5.3) -->
  <div
    class="relative flex min-h-42 w-full flex-col gap-2 rounded-card border border-t-4 border-surface-300 bg-surface px-4 pb-3 pt-3 text-left text-surface-900 transition-colors has-[button:hover]:bg-surface-50"
    :class="look.edge"
  >
    <span class="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-[0.06em]" :class="look.accent">
      <v-icon :icon="look.icon" size="16" />
      {{ look.label }}
      <span v-if="element.kind === 'task' && element.complete" class="ml-auto inline-flex items-center gap-1 text-xs font-semibold normal-case tracking-normal">
        <v-icon :icon="mdiCheckCircleOutline" size="16" />Complete
      </span>

      <span v-else-if="element.kind === 'task'" class="ml-auto text-xs font-semibold normal-case tabular-nums tracking-normal">{{ bar.done }} of {{ bar.total }}</span>

      <span v-else-if="element.kind === 'recommendation' && element.priority === 'high'" class="ml-auto inline-flex items-center gap-1 text-xs font-semibold normal-case tracking-normal">
        <v-icon :icon="mdiArrowUp" size="16" />High
      </span>
    </span>

    <h3 class="m-0 text-base">
      <button
        class="font-heading line-clamp-2 cursor-pointer border-0 bg-transparent p-0 text-left text-base font-semibold leading-snug text-surface-900 after:absolute after:inset-0 after:rounded-card after:content-[''] focus-visible:outline-none focus-visible:after:outline-2 focus-visible:after:outline-offset-2 focus-visible:after:outline-primary"
        type="button"
        @click="emit('open')"
      >{{ element.title }}</button>
    </h3>

    <span v-if="element.description" class="line-clamp-2 text-[13px] text-surface-600">{{ element.description }}</span>

    <span
      v-if="element.kind === 'task' && bar.total > 0"
      :aria-label="`${bar.done} of ${bar.total} done`"
      class="h-1.5 overflow-hidden rounded-full bg-surface-200"
      role="img"
    >
      <span class="block h-full rounded-full" :class="look.fill" :style="{ width: `${bar.percent}%` }" />
    </span>

    <span class="mt-auto flex items-center gap-2 border-t border-surface-200 pt-2.5 text-xs text-surface-600">
      <template v-if="uploading > 0">
        <v-icon class="text-primary" :icon="icons.sync" size="16" />
        <span>Uploading {{ uploading }}</span>
      </template>

      <template v-else>
        <v-icon :icon="element.kind === 'config' ? icons.upload : (picture?.kind === 'video' ? icons.video : icons.photo)" size="16" />
        <span>{{ files }}</span>
      </template>

      <span v-if="unsaved" class="inline-flex items-center gap-1 rounded-md bg-warning-container px-2 py-0.5 font-medium text-on-warning-container">
        <v-icon :icon="mdiCloudOffOutline" size="14" />Not saved yet
      </span>

      <span v-if="showSharing" class="rounded-md bg-surface-100 px-2 py-0.5 font-medium text-surface-700">{{ element.shared ? 'Shared' : 'Staff only' }}</span>

      <span :aria-label="`By ${element.created_by.name}`" class="ml-auto grid size-6 flex-none place-items-center rounded-full bg-linear-135 from-primary to-[#5aa9c4] text-[10px] font-bold text-white" role="img" :title="element.created_by.name">{{ initials(element.created_by.name) }}</span>
    </span>
  </div>
</template>

<script lang="ts" setup>
  import type { BoardElement } from '@/api/models'
  import { mdiArrowUp, mdiCheckCircleOutline, mdiCloudOffOutline } from '@mdi/js'
  import { computed } from 'vue'
  import { useLiveQuery } from '@/app/composables/useLiveQuery'
  import { icons } from '@/app/theme/icons'
  import { db } from '@/offline/db'
  import { cover, filesText, initials, KIND, progress } from '../board'

  // One element of a station's board (DBD 1.8 "Sticky note", the approved Stitch board): a white card
  // whose top edge, icon and label carry its kind's colour; the kind is always named, so colour is
  // never the only cue. A click anywhere on the card opens the element's sheet.
  const props = defineProps<{
    element: BoardElement
    /** Files of this element still going up from this device. */
    uploading?: number
    /** Staff see Shared or Staff only; a client sees only what is shared, so the chip says nothing. */
    showSharing?: boolean
  }>()

  const emit = defineEmits<{ open: [] }>()

  const look = computed(() => KIND[props.element.kind])
  const bar = computed(() => progress(props.element.items))
  const files = computed(() => filesText(props.element))
  const picture = computed(() => cover(props.element))
  const uploading = computed(() => props.uploading ?? 0)

  // Kept on this phone and not yet confirmed by the server (W14-6)
  const { value: row } = useLiveQuery(async () => (await db.visits.get(props.element.id)) ?? null)
  const unsaved = computed(() => row.value?.dirty === true)
</script>
