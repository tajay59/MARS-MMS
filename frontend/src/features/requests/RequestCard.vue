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
      <span class="font-mono text-xs font-medium text-surface-600" translate="no">{{ request.ref }}</span>
      <RequestStatusChip :status="request.status" />
    </span>

    <router-link
      class="text-base font-semibold leading-snug text-surface-900 no-underline after:absolute after:inset-0 after:rounded-3xl focus-visible:outline-none focus-visible:after:outline-2 focus-visible:after:outline-offset-2 focus-visible:after:outline-primary"
      :to="to"
    >{{ request.title }}</router-link>

    <span class="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-surface-600">
      <PriorityChip v-if="showsInList(request.priority)" :priority="request.priority" />
      <span class="font-mono text-xs font-medium" translate="no">{{ stationsLabel(request) }}</span>
      <template v-if="isStaff && request.org_name"><span aria-hidden="true">·</span><span>{{ request.org_name }}</span></template>
      <span aria-hidden="true">·</span><span>{{ formatListTime(request.updated_at) }}</span>
    </span>
  </li>
</template>

<script lang="ts" setup>
  import type { RequestSummary } from '@/api/models'
  import type { RouteLocationRaw } from 'vue-router'
  import { formatListTime } from '@/app/format'
  import { pressDown, pressPulse, pressUp } from '@/app/motion'
  import RequestStatusChip from '@/components/RequestStatusChip.vue'
  import PriorityChip from './PriorityChip.vue'
  import { showsInList, stationsLabel } from './requests'

  // One request in the phone list: reference and status, the title, then priority, stations and when.
  // The whole card is the link; pressing it shrinks it and lets it spring back.
  defineProps<{
    request: RequestSummary
    to: RouteLocationRaw
    isStaff: boolean
  }>()

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
