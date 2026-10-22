<template>
  <ModalSheet v-model="open" labelledby="am-h" :max-width="460">
    <div class="flex flex-col gap-4">
      <div>
        <h2 id="am-h" class="m-0 text-h2 text-surface-900">Add to {{ stationName }}</h2>
        <p v-if="stationCode" class="m-0 mt-0.5 font-mono text-xs text-surface-600" translate="no">{{ stationCode }}</p>
      </div>

      <fieldset class="m-0 flex min-w-0 flex-col gap-2 border-0 p-0">
        <legend class="mb-2 p-0 text-label text-surface-900">Which part of the visit is it from?</legend>

        <v-btn-toggle
          v-model="phase"
          class="self-start"
          color="primary"
          density="comfortable"
          divided
          mandatory
          variant="outlined"
        >
          <v-btn v-for="p in PHASES" :key="p" :value="p">{{ PHASE_LABEL[p] }}</v-btn>
        </v-btn-toggle>
      </fieldset>

      <ul class="m-0 flex list-none flex-col gap-1 p-0">
        <li v-if="touch">
          <button :class="optionClass" type="button" @click="photoInput?.click()">
            <span :class="iconClass"><v-icon :icon="icons.photo" size="22" /></span>
            <span class="flex flex-col"><span class="font-medium text-surface-900">Take a photo</span><small class="text-surface-600">Opens the camera</small></span>
          </button>
        </li>

        <li v-if="touch">
          <button :class="optionClass" type="button" @click="videoInput?.click()">
            <span :class="iconClass"><v-icon :icon="icons.video" size="22" /></span>
            <span class="flex flex-col"><span class="font-medium text-surface-900">Record a video</span><small class="text-surface-600">Up to about 2 minutes works best</small></span>
          </button>
        </li>

        <li>
          <button :class="optionClass" type="button" @click="libraryInput?.click()">
            <span :class="iconClass"><v-icon :icon="mdiImageMultipleOutline" size="22" /></span>
            <span class="flex flex-col"><span class="font-medium text-surface-900">{{ touch ? 'Choose from your phone' : 'Choose files' }}</span><small class="text-surface-600">Photos and videos</small></span>
          </button>
        </li>
      </ul>

      <div class="flex justify-end">
        <v-btn class="text-primary" variant="text" @click="open = false">Cancel</v-btn>
      </div>
    </div>
  </ModalSheet>

  <!-- Outside the dialog: the picker's answer must land even as the sheet closes -->
  <input
    ref="photoInput"
    accept="image/*"
    aria-hidden="true"
    capture="environment"
    class="hidden"
    tabindex="-1"
    type="file"
    @change="picked"
  >

  <input
    ref="videoInput"
    accept="video/*"
    aria-hidden="true"
    capture="environment"
    class="hidden"
    tabindex="-1"
    type="file"
    @change="picked"
  >

  <input
    ref="libraryInput"
    accept="image/*,video/*"
    aria-hidden="true"
    class="hidden"
    multiple
    tabindex="-1"
    type="file"
    @change="picked"
  >
</template>

<script lang="ts" setup>
  import { mdiImageMultipleOutline } from '@mdi/js'
  import { ref } from 'vue'
  import { icons } from '@/app/theme/icons'
  import ModalSheet from '@/components/ModalSheet.vue'
  import { type Phase, PHASE_LABEL, PHASES } from './media'

  // Add photos or video to a station (board "W11 screens" 1 and 2): the phase first, then the
  // camera, the video recorder or the library. A phone offers all three; a computer only the file
  // picker. The files go to the page's upload queue, which shrinks and sends them.
  defineProps<{
    stationName: string
    stationCode?: string | null
  }>()

  const emit = defineEmits<{ pick: [files: File[], phase: Phase] }>()
  const open = defineModel<boolean>({ required: true })

  // One row of the add sheet, the same on the dialog and the phone sheet
  const optionClass = 'grid w-full cursor-pointer grid-cols-[40px_1fr] items-center gap-3 rounded-lg border-0 bg-transparent p-2.5 text-left hover:bg-surface-100'
  const iconClass = 'grid size-10 place-items-center rounded-full bg-primary-100 text-primary-700'

  const phase = ref<Phase>('during')
  const touch = typeof globalThis.matchMedia === 'function' && globalThis.matchMedia('(pointer: coarse)').matches
  const photoInput = ref<HTMLInputElement | null>(null)
  const videoInput = ref<HTMLInputElement | null>(null)
  const libraryInput = ref<HTMLInputElement | null>(null)

  function picked (event: Event): void {
    const input = event.target as HTMLInputElement
    const files = [...(input.files ?? [])]
    // Clearing lets the same file be chosen again after it failed
    input.value = ''
    if (files.length > 0) {
      emit('pick', files, phase.value)
      open.value = false
    }
  }
</script>
