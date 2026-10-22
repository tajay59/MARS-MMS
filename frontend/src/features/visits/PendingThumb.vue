<template>
  <li class="relative flex w-33 flex-none flex-col overflow-hidden rounded-lg border bg-surface-50 max-md:w-28" :class="item.state === 'failed' ? 'border-error' : 'border-surface-200'">
    <div class="flex aspect-4/3 items-center justify-center bg-surface-100" :class="item.state === 'failed' ? 'text-error' : 'text-surface-500'">
      <v-icon :icon="item.state === 'failed' ? mdiAlertCircleOutline : (item.kind === 'video' ? icons.video : icons.photo)" size="28" />
    </div>

    <template v-if="item.state === 'failed'">
      <div class="flex flex-col gap-1.5 px-2 pb-2 pt-1.5 text-xs text-surface-700" role="alert">
        <span><b class="font-semibold text-surface-900"><span class="font-mono" translate="no">{{ item.name }}</span> didn’t go.</b> {{ item.error }}</span>

        <span class="flex flex-wrap gap-1.5">
          <v-btn size="small" variant="outlined" @click="emit('retry')">Try again</v-btn>
          <v-btn size="small" variant="outlined" @click="emit('discard')">Remove</v-btn>
        </span>
      </div>
    </template>

    <template v-else>
      <div
        :aria-label="`${item.name}: ${wording}`"
        :aria-valuemax="100"
        :aria-valuemin="0"
        :aria-valuenow="item.state === 'uploading' ? percent : undefined"
        class="mx-2 mt-1.5 h-1.5 overflow-hidden rounded-full bg-surface-200"
        role="progressbar"
      >
        <div class="h-full rounded-full bg-primary" :class="item.state === 'uploading' ? '' : 'opacity-35'" :style="{ width: item.state === 'uploading' ? `${percent}%` : '100%' }" />
      </div>

      <div class="flex flex-col gap-1 px-2 pb-2 pt-1.5 text-xs text-surface-700">
        <span><b class="font-semibold text-surface-900">{{ wording }}</b> <span class="font-mono" translate="no">{{ item.name }}</span></span>
        <span v-if="item.state === 'uploading'"><v-btn size="small" variant="outlined" @click="emit('discard')">Cancel</v-btn></span>
      </div>
    </template>
  </li>
</template>

<script lang="ts" setup>
  import type { PendingMedia } from '@/app/composables/useVisitMedia'
  import { mdiAlertCircleOutline } from '@mdi/js'
  import { computed } from 'vue'
  import { icons } from '@/app/theme/icons'

  // A file on its way to a station: waiting its turn, being shrunk, going up, or being put on the
  // station (board "W11 screens" 1 and 2). A failed one says why and offers Try again, which carries
  // on from the step that failed, or Remove.
  const props = defineProps<{ item: PendingMedia }>()

  const emit = defineEmits<{ retry: [], discard: [] }>()

  const percent = computed(() => Math.round(props.item.progress * 100))
  const wording = computed(() => {
    switch (props.item.state) {
      case 'uploading': {
        return `${percent.value}% of`
      }
      case 'preparing': {
        return 'Preparing'
      }
      case 'saving': {
        return 'Adding'
      }
      default: {
        return 'Waiting'
      }
    }
  })
</script>
