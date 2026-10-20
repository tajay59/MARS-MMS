<template>
  <div class="flex flex-col gap-2">
    <div class="flex items-center justify-between gap-2">
      <label :id="`${id}-label`" class="text-label text-surface-900" :for="id">Photos <span class="font-normal text-surface-600">(optional)</span></label>
      <span v-if="files.length > 0" class="text-xs tabular-nums text-surface-600">{{ files.length }} of {{ MAX_STAGED_PHOTOS }} attached</span>
    </div>

    <div
      class="flex flex-col items-center gap-1.5 rounded-card border-[1.5px] border-dashed px-4 py-4 text-center"
      :class="[dragging ? 'border-primary bg-primary-50' : 'border-surface-500 bg-surface-50', disabled ? 'opacity-60' : '']"
      @dragenter.prevent="dragging = !disabled"
      @dragleave.prevent="dragging = false"
      @dragover.prevent
      @drop.prevent="onDrop"
    >
      <v-btn
        :aria-describedby="`${id}-hint`"
        color="primary"
        :disabled="disabled || files.length >= MAX_STAGED_PHOTOS"
        :prepend-icon="icons.photo"
        variant="outlined"
        @click="picker?.click()"
      >Take a photo or choose pictures</v-btn>

      <div :id="`${id}-hint`" class="text-xs text-surface-600">PNG or JPEG · up to 10 MB each · or drop them here. They go up when you save.</div>

      <!-- Phones offer the camera and the library for an image input -->
      <input
        :id="id"
        ref="picker"
        accept="image/png,image/jpeg"
        :aria-labelledby="`${id}-label`"
        class="sr-only"
        data-testid="model-photo-input"
        multiple
        tabindex="-1"
        type="file"
        @change="onPick"
      >
    </div>

    <p v-if="problem" class="m-0 text-sm text-error" role="alert">{{ problem }}</p>

    <ul v-if="files.length > 0" aria-label="Photos to attach" class="m-0 flex list-none flex-col gap-1.5 p-0">
      <li v-for="(file, index) in files" :key="`${file.name}-${file.size}`" class="flex items-center gap-3 rounded-card bg-surface-50 px-2.5 py-2">
        <img
          v-if="previews[index]"
          alt=""
          class="size-9 shrink-0 rounded-md object-cover"
          :src="previews[index]"
        >

        <v-icon v-else class="shrink-0 text-surface-600" :icon="mdiImageOutline" size="28" />

        <div class="min-w-0 grow">
          <div class="truncate text-sm font-medium text-surface-900">{{ file.name }}</div>
          <div class="text-xs tabular-nums text-surface-600">{{ stateText(file) }}</div>
        </div>

        <v-btn
          v-if="!disabled"
          :aria-label="`Remove ${file.name}`"
          icon
          size="36"
          variant="text"
          @click="remove(index)"
        >
          <v-icon :icon="mdiClose" size="18" />
        </v-btn>
      </li>
    </ul>
  </div>
</template>

<script lang="ts" setup>
  import { mdiClose, mdiImageOutline } from '@mdi/js'
  import { onBeforeUnmount, ref, watch } from 'vue'
  import { icons } from '@/app/theme/icons'
  import { formatBytes } from '@/features/stations/documents'
  import { MAX_STAGED_PHOTOS, photoProblem } from './sensorForms'

  // Pictures to attach to a sensor model as it is saved (W6-12). They stay on this device until the
  // model exists, then the form sends them one by one. `states` says how each one is getting on.
  const props = defineProps<{
    id: string
    disabled?: boolean
    /** Per file name: what the form is doing with it ("Sending…", "Added", why it failed). */
    states?: Record<string, string>
  }>()

  const files = defineModel<File[]>({ required: true })
  const picker = ref<HTMLInputElement | null>(null)
  const dragging = ref(false)
  const problem = ref<string | null>(null)
  const previews = ref<(string | null)[]>([])

  function add (list: FileList | null | undefined): void {
    problem.value = null
    const next = [...files.value]
    for (const file of list ?? []) {
      const why = photoProblem(file, next)
      if (why) {
        problem.value = why
        continue
      }
      next.push(file)
    }
    files.value = next
  }

  function onPick (event: Event): void {
    const input = event.target as HTMLInputElement
    add(input.files)
    input.value = ''
  }

  function onDrop (event: DragEvent): void {
    dragging.value = false
    if (!props.disabled) {
      add(event.dataTransfer?.files)
    }
  }

  function remove (index: number): void {
    problem.value = null
    files.value = files.value.filter((_, i) => i !== index)
  }

  function stateText (file: File): string {
    return props.states?.[file.name] ?? formatBytes(file.size)
  }

  // Small previews from object URLs, released as soon as the list changes
  function release (): void {
    for (const url of previews.value) {
      if (url) {
        URL.revokeObjectURL(url)
      }
    }
  }

  watch(files, list => {
    release()
    previews.value = list.map(f => typeof URL.createObjectURL === 'function' ? URL.createObjectURL(f) : null)
  }, { immediate: true })
  onBeforeUnmount(release)
</script>
