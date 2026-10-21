<template>
  <div class="flex flex-col gap-4">
    <v-text-field
      aria-label="Search the queue by reference, title or station"
      autocomplete="off"
      class="[&_.v-field]:bg-surface-50"
      clearable
      flat
      hide-details
      :model-value="filters.q"
      name="q"
      placeholder="Search reference, title or station"
      :prepend-inner-icon="mdiMagnify"
      spellcheck="false"
      type="search"
      variant="solo-inverted"
      @update:model-value="emit('change', { q: $event ?? '' })"
    />

    <!-- Priority first. Country and category are tables when there is room (a row to pick, 400 px at most, then they scroll) and chips when there is not -->
    <template v-for="group in groups" :key="group.field">
      <div
        v-if="tables && group.field !== 'priority'"
        class="flex flex-col gap-2"
      >
        <h3 :id="`q-${group.field}`" class="m-0 text-xs font-semibold uppercase tracking-wide text-surface-600">{{ group.label }}</h3>

        <FilterTable
          :label="group.label"
          :rows="rowsOf(group)"
          :selected="filters[group.field]"
          @pick="pick(group.field, $event)"
        />
      </div>

      <div
        v-else
        :aria-labelledby="`q-${group.field}`"
        class="flex flex-col gap-2"
        role="group"
      >
        <h3 :id="`q-${group.field}`" class="m-0 text-xs font-semibold uppercase tracking-wide text-surface-600">{{ group.label }}</h3>

        <div class="flex flex-wrap gap-1.5">
          <FilterChip
            :active="filters[group.field] === null"
            :count="group.any"
            label="Any"
            @click="pick(group.field, null)"
          />

          <FilterChip
            v-for="option in group.options"
            :key="option.value"
            :active="filters[group.field] === option.value"
            :count="option.count"
            :label="option.label"
            @click="pick(group.field, option.value)"
          />
        </div>
      </div>
    </template>

    <button
      v-if="filtered"
      class="self-start rounded-md px-2 py-1.5 text-sm font-medium text-primary hover:bg-surface-100"
      type="button"
      @click="emit('clear')"
    >Clear filters</button>
  </div>
</template>

<script lang="ts" setup>
  import type { FilterGroup, QueueFilters } from './queue'
  import { mdiMagnify } from '@mdi/js'
  import FilterChip from './FilterChip.vue'
  import FilterTable from './FilterTable.vue'

  // The queue's search and filters (PRD REQ-7): search, then priority, country and category with
  // how many requests each leaves. On a phone it sits in a bottom sheet and on a desktop in the
  // pane, so the markup is here once and the page decides where it goes.
  const props = defineProps<{
    filters: QueueFilters
    groups: FilterGroup[]
    filtered: boolean
    /** Country and category as tables (there is room), not chips */
    tables: boolean
  }>()

  const emit = defineEmits<{ change: [patch: Partial<QueueFilters>], clear: [] }>()

  function rowsOf (group: FilterGroup): { value: string | null, label: string, count: number }[] {
    return [{ value: null, label: 'Any', count: group.any }, ...group.options]
  }

  // A value already picked is let go by picking it again; "Any" always clears the field
  function pick (field: FilterGroup['field'], value: string | null): void {
    emit('change', { [field]: value === null || props.filters[field] === value ? null : value })
  }
</script>
