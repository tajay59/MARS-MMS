<template>
  <!-- The map marker's shape at list size (DBD): the shape tells statuses apart without colour -->
  <svg aria-hidden="true" class="size-2.5 shrink-0" :class="look.mark" viewBox="0 0 10 10">
    <circle
      v-if="status === 'operational'"
      cx="5"
      cy="5"
      fill="currentColor"
      r="5"
    />

    <path v-else-if="status === 'degraded'" d="M5 0L10 10H0Z" fill="currentColor" />

    <template v-else-if="status === 'offline'">
      <rect fill="currentColor" height="10" width="10" />
      <path d="M3 3L7 7M7 3L3 7" stroke="#fff" stroke-width="1.4" />
    </template>

    <circle
      v-else
      cx="5"
      cy="5"
      fill="none"
      r="4"
      stroke="currentColor"
      stroke-width="2"
    />
  </svg>
</template>

<script lang="ts" setup>
  import type { StationStatus } from '@/api/models'
  import { computed } from 'vue'
  import { statusLook } from '@/features/stations/stations'

  const props = defineProps<{ status: StationStatus }>()

  const look = computed(() => statusLook[props.status])
</script>
