<template>
  <li
    class="relative flex items-center gap-4 rounded-3xl px-3 py-3 transition-colors duration-150 active:bg-surface-100"
    @click="keyPress"
    @pointercancel="release"
    @pointerdown="press"
    @pointerleave="release"
    @pointerup="release"
  >
    <span class="grid size-14 shrink-0 place-items-center rounded-full" :class="look.chip">
      <v-icon :icon="look.icon" size="28" />
    </span>

    <span class="flex min-w-0 grow flex-col gap-0.5">
      <router-link
        class="truncate text-base font-medium text-surface-900 no-underline after:absolute after:inset-0 after:rounded-3xl focus-visible:outline-none focus-visible:after:outline-2 focus-visible:after:outline-offset-2 focus-visible:after:outline-primary"
        :to="to"
      >{{ station.name }}</router-link>

      <span class="truncate text-sm text-surface-600">
        <template v-if="isStaff && station.owner_org_name">{{ station.owner_org_name }} · </template>{{ countryName(station.country) }}
      </span>

      <span v-if="overdue" class="mt-1">
        <CalibrationDueChip :due="station.next_calibration_due_at" state="overdue" :time-zone="station.time_zone" />
      </span>
    </span>

    <span class="flex shrink-0 flex-col items-end gap-2 self-start pt-0.5">
      <span class="font-mono text-xs font-medium text-surface-600" translate="no">{{ station.code }}</span>

      <!-- The avatar's icon already tells the status by shape; the dot echoes it, and the words are here for a screen reader -->
      <span :aria-label="look.label" class="size-2.5 rounded-full bg-current" :class="look.mark" role="img" />
    </span>
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

  // One station in the phone list (a big status avatar, the name and where it is, the code and a
  // status dot at the right). The whole card is the link; pressing it shrinks it and lets it spring back.
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
