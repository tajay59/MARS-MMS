<template>
  <div
    class="flex items-start gap-3 rounded-md border-l-4 px-4 py-3 text-sm"
    :class="tone.box"
    :role="type === 'error' || type === 'warning' ? 'alert' : 'status'"
  >
    <v-icon class="mt-px shrink-0" :class="tone.icon" :icon="icon ?? tone.defaultIcon" size="20" />

    <div class="min-w-0 grow">
      <slot />
    </div>
  </div>
</template>

<script lang="ts" setup>
  import { mdiAlertCircleOutline, mdiAlertOutline, mdiCheckCircleOutline, mdiInformationOutline } from '@mdi/js'
  import { computed } from 'vue'

  // A message above a form or page (DBD feedback colours). Errors and warnings are announced at once.
  const props = defineProps<{
    type: 'success' | 'info' | 'warning' | 'error'
    icon?: string
  }>()

  const tones = {
    success: { box: 'bg-success-container text-on-success-container border-success', icon: 'text-success', defaultIcon: mdiCheckCircleOutline },
    info: { box: 'bg-info-container text-on-info-container border-info', icon: 'text-info', defaultIcon: mdiInformationOutline },
    warning: { box: 'bg-warning-container text-on-warning-container border-warning', icon: 'text-warning', defaultIcon: mdiAlertOutline },
    error: { box: 'bg-error-container text-on-error-container border-error', icon: 'text-error', defaultIcon: mdiAlertCircleOutline },
  } as const

  const tone = computed(() => tones[props.type])
</script>
