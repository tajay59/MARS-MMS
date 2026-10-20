<template>
  <li
    class="relative flex gap-3 rounded-card px-3 py-2.5 transition-colors duration-150 max-sm:gap-4 max-sm:rounded-3xl"
    :class="active ? 'bg-primary-50' : 'hover:bg-surface-100 active:bg-surface-200'"
  >
    <ModelPhoto
      class="size-14 shrink-0 rounded-lg max-sm:rounded-full"
      :document-id="model.cover_document_id"
      :icon="kindIcon(model.kind)"
    />

    <div class="flex min-w-0 grow flex-col gap-1">
      <div class="flex items-center justify-between gap-2">
        <router-link
          :aria-current="active ? 'page' : undefined"
          class="truncate font-medium text-surface-900 no-underline after:absolute after:inset-0 after:rounded-card max-sm:after:rounded-3xl focus-visible:outline-none focus-visible:after:outline-2 focus-visible:after:outline-offset-2 focus-visible:after:outline-primary"
          :to="to"
        >{{ model.manufacturer }} {{ model.model }}</router-link>

        <span class="shrink-0 rounded bg-surface-100 px-1.5 py-0.5 text-xs text-surface-700">{{ kindLabel(model.kind) }}</span>
      </div>

      <div v-if="model.parameters.length > 0" class="flex flex-wrap items-center gap-1">
        <span
          v-for="code in model.parameters.slice(0, 4)"
          :key="code"
          class="rounded-full bg-surface-100 px-2 py-px font-mono text-xs text-surface-800"
          translate="no"
        >{{ code }}</span>

        <span v-if="model.parameters.length > 4" class="text-xs text-surface-600">+{{ model.parameters.length - 4 }}</span>
      </div>

      <div class="flex flex-wrap items-center justify-between gap-x-3 gap-y-0.5 text-xs text-surface-600">
        <span class="font-medium" :class="total > 0 ? 'text-primary' : ''">{{ unitsRegistered(model.unit_counts) }}</span>

        <span v-if="hint" class="truncate font-mono" translate="no">{{ hint }}</span>
      </div>

      <ul v-if="breakdown.length > 1" aria-label="Units by status" class="m-0 flex list-none flex-wrap gap-x-3 gap-y-0.5 p-0 text-xs text-surface-600">
        <li v-for="b in breakdown" :key="b.status" class="inline-flex items-center gap-1">
          <UnitStatusDot :status="b.status" />{{ b.text }}
        </li>
      </ul>
    </div>
  </li>
</template>

<script lang="ts" setup>
  import type { SensorModelOut } from '@/api/models'
  import type { RouteLocationRaw } from 'vue-router'
  import { computed } from 'vue'
  import { kindLabel } from '@/features/stations/stations'
  import ModelPhoto from './ModelPhoto.vue'
  import { kindIcon, specHint, unitBreakdown, unitsRegistered, unitTotal } from './sensors'
  import UnitStatusDot from './UnitStatusDot.vue'

  // One model in the catalogue list: its photo (or the icon for its kind), name, what it measures,
  // how many units there are and in what state. The whole row is the link.
  const props = defineProps<{
    model: SensorModelOut
    active: boolean
    to: RouteLocationRaw
  }>()

  const total = computed(() => unitTotal(props.model.unit_counts))
  const breakdown = computed(() => unitBreakdown(props.model.unit_counts))
  const hint = computed(() => specHint(props.model))
</script>
