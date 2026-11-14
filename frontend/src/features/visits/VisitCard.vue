<template>
  <li
    class="relative flex flex-col gap-1.5 rounded-3xl px-3 py-3.5 transition-colors duration-150 active:bg-surface-100"
    @click="keyPress"
    @pointercancel="release"
    @pointerdown="press"
    @pointerleave="release"
    @pointerup="release"
  >
    <span class="flex items-center justify-between gap-2">
      <span class="font-mono text-xs font-medium text-surface-600" translate="no">{{ visit.ref }}</span>
      <VisitStatusChip :status="visit.status" />
    </span>

    <router-link
      class="text-base font-semibold leading-snug text-surface-900 no-underline after:absolute after:inset-0 after:rounded-3xl focus-visible:outline-none focus-visible:after:outline-2 focus-visible:after:outline-offset-2 focus-visible:after:outline-primary"
      :to="to"
    >{{ visit.request_title }}</router-link>

    <span class="text-sm text-surface-600">{{ formatWhen(visit.planned_start, zone) }} · {{ stationNames(visit) }}</span>
  </li>
</template>

<script lang="ts" setup>
  import type { VisitOut } from '@/api/models'
  import type { RouteLocationRaw } from 'vue-router'
  import { computed } from 'vue'
  import { pressDown, pressPulse, pressUp } from '@/app/motion'
  import VisitStatusChip from '@/components/VisitStatusChip.vue'
  import { formatWhen, stationNames, visitZone } from './visits'

  // One visit in the phone list: reference and status, the request's title, then when and where.
  // The whole card is the link; pressing it shrinks it and lets it spring back.
  const props = defineProps<{ visit: VisitOut, to: RouteLocationRaw }>()

  const zone = computed(() => visitZone(props.visit))

  function press (event: PointerEvent): void {
    if (event.button === 0) {
      pressDown(event.currentTarget as Element)
    }
  }

  function release (event: Event): void {
    pressUp(event.currentTarget as Element)
  }

  function keyPress (event: MouseEvent): void {
    if (event.detail === 0) {
      pressPulse(event.currentTarget as Element)
    }
  }
</script>
