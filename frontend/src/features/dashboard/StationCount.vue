<template>
  <span
    v-if="count > 0"
    class="inline-flex h-6 min-w-9 items-center justify-center gap-1 rounded-full px-2 text-xs font-medium tabular-nums"
    :class="look.chip"
  >
    <v-icon aria-hidden="true" :icon="look.icon" size="14" />{{ count }}<span class="sr-only"> {{ look.label }}</span>
  </span>

  <span v-else class="text-xs tabular-nums text-surface-600">0<span class="sr-only"> {{ look.label }}</span></span>
</template>

<script lang="ts" setup>
  import { computed } from 'vue'
  import { isStatus, statusLook } from '@/features/stations/stations'

  // A number of stations in one status: icon, number and colour together, a plain zero otherwise
  const props = defineProps<{ count: number, status: string }>()

  const look = computed(() => statusLook[isStatus(props.status) ? props.status : 'decommissioned'])
</script>
