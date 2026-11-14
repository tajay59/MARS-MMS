<template>
  <div
    class="flex min-w-0 flex-col gap-0.5 rounded-card border-l-4 bg-surface-50 px-4 py-3.5"
    :class="toneClass[tone]"
  >
    <span class="text-sm leading-[18px] text-surface-600" :class="compact ? '' : 'min-h-9'">{{ label }}</span>

    <div class="font-heading tabular-nums text-surface-900" :class="compact ? 'text-[28px] leading-8' : 'text-kpi'">
      <template v-if="unavailable">
        <span aria-hidden="true" class="text-surface-500">–</span>
        <span class="sr-only">Needs a connection</span>
      </template>

      <v-skeleton-loader v-else-if="loading" class="my-1 w-12" type="text" />
      <template v-else>{{ count(value) }}</template>
    </div>

    <span v-if="unavailable" class="text-xs text-surface-600">Needs a connection</span>
    <span v-else-if="caption" class="text-xs text-surface-600">{{ caption }}</span>

    <router-link
      v-if="to && !unavailable"
      class="mt-1 inline-flex min-h-6 w-fit items-center text-sm font-medium text-primary no-underline hover:underline"
      :to="to"
    >{{ link }}<span aria-hidden="true"> →</span></router-link>
  </div>
</template>

<script lang="ts" setup>
  import type { Tone } from './dashboard'
  import type { RouteLocationRaw } from 'vue-router'
  import { count, toneClass } from './dashboard'

  // One number that links to the list behind it (DBD "Dashboards"). The coloured edge is for
  // things that need someone and is passed already decided (`toneOf`), so a zero is plain.
  withDefaults(defineProps<{
    label: string
    value?: number | null
    to?: RouteLocationRaw
    link?: string
    tone?: Tone
    caption?: string
    loading?: boolean
    /** The figure comes from the server and there is no connection. */
    unavailable?: boolean
    /** A smaller number, for the phone. */
    compact?: boolean
  }>(), { value: null, to: undefined, link: 'Open', tone: 'none', caption: undefined })
</script>
