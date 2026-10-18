<template>
  <span class="inline-flex h-6 shrink-0 items-center gap-1 whitespace-nowrap rounded-full px-2.5 text-xs font-medium" :class="look">
    <v-icon v-if="state === 'overdue'" class="-ml-0.5" :icon="mdiCalendarAlertOutline" size="14" />{{ label }}
  </span>
</template>

<script lang="ts" setup>
  import type { DueState } from '@/features/stations/stations'
  import { mdiCalendarAlertOutline } from '@mdi/js'
  import { computed } from 'vue'
  import { dueLabel, dueLook } from '@/features/stations/stations'

  // Calibration due (CAL-3, DBD "Other status sets"): in date, due within 30 days, overdue, no interval
  const props = defineProps<{
    state: DueState | null
    due?: string | null
    /** The station's zone: the day is the one on the station's calendar. */
    timeZone?: string | null
  }>()

  const look = computed(() => dueLook[props.state ?? 'none'])
  const label = computed(() => dueLabel(props.state, props.due, props.timeZone))
</script>
