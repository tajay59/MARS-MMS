<template>
  <li
    class="relative flex flex-col gap-1 rounded-card px-3 py-2.5 transition-colors duration-150"
    :class="active ? 'bg-primary-50' : 'hover:bg-surface-100 active:bg-surface-200'"
  >
    <router-link
      :aria-current="active ? 'page' : undefined"
      class="font-mono font-medium text-surface-900 no-underline after:absolute after:inset-0 after:rounded-card focus-visible:outline-none focus-visible:after:outline-2 focus-visible:after:outline-offset-2 focus-visible:after:outline-primary"
      :to="to"
      translate="no"
    >{{ unit.serial }}</router-link>

    <span class="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-xs text-surface-700">
      <span>{{ reviewLine(unit) }}</span>
      <span v-if="unit.station">{{ unit.station.name }}</span>
      <NeedsReviewChip />
    </span>
  </li>
</template>

<script lang="ts" setup>
  import type { SensorUnitOut } from '@/api/models'
  import type { RouteLocationRaw } from 'vue-router'
  import NeedsReviewChip from './NeedsReviewChip.vue'
  import { reviewLine } from './sensors'

  // One unit that was added from the field and waits for a check, in the pane's Needs review list.
  // The whole row is the link to the model it belongs to, with the unit picked.
  defineProps<{
    unit: SensorUnitOut
    active: boolean
    to: RouteLocationRaw
  }>()
</script>
