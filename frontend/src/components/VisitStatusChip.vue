<template>
  <span class="inline-flex h-6 shrink-0 items-center gap-1 whitespace-nowrap rounded-full pl-2 pr-2.5 text-xs font-medium" :class="look.chip">
    <v-icon :icon="look.icon" size="14" />{{ look.label }}
  </span>
</template>

<script lang="ts" setup>
  import { computed } from 'vue'
  import { lookOfVisit } from '@/features/visits/visits'

  // A visit's status: icon, word and shade together, never colour alone. Not a request status
  // colour: those are reserved for requests and stations (DBD Status colours).
  const props = defineProps<{ status: string }>()

  const look = computed(() => lookOfVisit(props.status))
</script>
