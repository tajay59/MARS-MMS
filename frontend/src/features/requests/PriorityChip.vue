<template>
  <span class="inline-flex h-6 shrink-0 items-center gap-1 whitespace-nowrap rounded-full pl-2 pr-2.5 text-xs font-medium" :class="priorityChip[priority] ?? priorityChip.normal">
    <v-icon v-if="icon" :icon="icon" size="14" />{{ priorityLabel(priority) }}
  </span>
</template>

<script lang="ts" setup>
  import { mdiAlertOutline, mdiArrowUp } from '@mdi/js'
  import { computed } from 'vue'
  import { priorityChip, priorityLabel } from './requests'

  // A request's priority. High and Urgent carry an icon as well as their colour.
  const props = defineProps<{ priority: string }>()

  const icon = computed(() => props.priority === 'urgent' ? mdiAlertOutline : (props.priority === 'high' ? mdiArrowUp : null))
</script>
