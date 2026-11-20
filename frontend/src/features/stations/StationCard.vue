<template>
  <li
    class="relative flex items-center gap-3 rounded-card px-3 py-3 transition-colors duration-150 active:bg-surface-100"
    @click="keyPress"
    @pointercancel="release"
    @pointerdown="press"
    @pointerleave="release"
    @pointerup="release"
  >
    <span aria-hidden="true" class="grid size-10 shrink-0 place-items-center rounded-full" :class="look.chip">
      <v-icon :icon="look.icon" size="20" />
    </span>

    <span class="flex min-w-0 grow flex-col gap-0.5">
      <router-link
        class="truncate text-base font-medium text-surface-900 no-underline after:absolute after:inset-0 after:rounded-card focus-visible:outline-none focus-visible:after:outline-2 focus-visible:after:outline-offset-2 focus-visible:after:outline-primary"
        :to="to"
      >{{ station.name }}</router-link>

      <!-- Status as a word, not only an icon and a colour (DBD "Status first") -->
      <span class="truncate text-sm text-surface-600">
        <span class="font-medium text-surface-900">{{ look.label }}</span> · <template v-if="isStaff && station.owner_org_name">{{ station.owner_org_name }} · </template>{{ countryName(station.country) }}
      </span>

      <span v-if="overdue" class="mt-1">
        <CalibrationDueChip :due="station.next_calibration_due_at" state="overdue" :time-zone="station.time_zone" />
      </span>
    </span>

    <span class="shrink-0 self-start pt-0.5 font-mono text-xs font-medium text-surface-600" translate="no">{{ station.code }}</span>
  </li>
</template>

<script lang="ts" setup>
  import type { StationSummary } from '@/api/models'
  import type { RouteLocationRaw } from 'vue-router'
  import { computed } from 'vue'
  import { countryName } from '@/app/countries'
  import { pressDown, pressPulse, pressUp } from '@/app/motion'
  import CalibrationDueChip from '@/components/CalibrationDueChip.vue'
  import { dueState, lookOf } from './stations'

  // One station in the phone list: a status icon, the name, the status in words and where it is,
  // and the code at the right. The whole card is the link; pressing it shrinks it and lets it spring back.
  const props = defineProps<{
    station: StationSummary
    to: RouteLocationRaw
    isStaff: boolean
    now: Date
  }>()

  const look = computed(() => lookOf(props.station.status))
  const overdue = computed(() => dueState(props.station.next_calibration_due_at, props.now) === 'overdue')

  function press (event: PointerEvent): void {
    if (event.button === 0) {
      pressDown(event.currentTarget as Element)
    }
  }

  function release (event: Event): void {
    pressUp(event.currentTarget as Element)
  }

  // Enter on the link clicks without pointer events, so it gets both in one go
  function keyPress (event: MouseEvent): void {
    if (event.detail === 0) {
      pressPulse(event.currentTarget as Element)
    }
  }
</script>
