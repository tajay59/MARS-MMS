<template>
  <div v-if="state === 'checking'" class="mt-0.75 inline-flex items-center gap-1.25 text-xs text-on-info-container">
    <v-icon :icon="mdiClockOutline" size="14" />Checking file… it can be downloaded in a moment
  </div>

  <div v-else-if="state === 'failed'" class="mt-0.75 inline-flex items-center gap-1.25 text-xs text-error" role="alert">
    <v-icon :icon="mdiAlertCircleOutline" size="14" />{{ failReason(doc.scan_status === 'infected' ? 'infected' : null) }}
  </div>
</template>

<script lang="ts" setup>
  import type { DocumentOut } from '@/api/models'
  import { mdiAlertCircleOutline, mdiClockOutline } from '@mdi/js'
  import { computed } from 'vue'
  import { docState, failReason } from './documents'

  // What a file that isn't downloadable yet is waiting for (media's size, type and virus checks)
  const props = defineProps<{ doc: Pick<DocumentOut, 'status' | 'scan_status'> }>()

  const state = computed(() => docState(props.doc))
</script>
