<template>
  <span class="inline-flex h-6 items-center gap-1.5 whitespace-nowrap rounded-full bg-surface-100 px-2.5 text-xs font-medium text-surface-800">
    <UnitStatusDot :status="status" />{{ unitStatusLabel[status] ?? status }}
  </span>
</template>

<script lang="ts" setup>
  import { unitStatusLabel } from './sensors'
  import UnitStatusDot from './UnitStatusDot.vue'

  // A unit's status as a neutral chip with a dot. The reserved status colours stay with requests,
  // stations and calibration.
  defineProps<{
    status: string
  }>()
</script>
