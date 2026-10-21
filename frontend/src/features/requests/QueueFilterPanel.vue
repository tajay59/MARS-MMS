<template>
  <div class="flex flex-col gap-4">
    <v-text-field
      aria-label="Search the queue by reference, title or station"
      autocomplete="off"
      class="[&_.v-field]:bg-surface-100"
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

        <div class="max-h-[400px] overflow-y-auto rounded-lg border border-surface-300">
          <table class="w-full border-collapse text-sm">
            <caption class="sr-only">{{ group.label }}: pick a row to filter the queue by it</caption>

            <thead>
              <tr class="text-left">
                <th class="sticky top-0 bg-surface-100 px-3 py-2 text-xs font-medium text-surface-700" scope="col">{{ group.label }}</th>
                <th class="sticky top-0 bg-surface-100 px-3 py-2 text-right text-xs font-medium text-surface-700" scope="col">Requests</th>
              </tr>
            </thead>

            <tbody>
              <tr
                v-for="row in rowsOf(group)"
                :key="row.value ?? 'any'"
                class="cursor-pointer border-t border-surface-200 hover:bg-surface-100"
                :class="filters[group.field] === row.value ? 'bg-primary-100 font-medium text-primary-800 hover:bg-primary-100 dark:bg-primary-800 dark:text-primary-100 dark:hover:bg-primary-800' : 'text-surface-900'"
                @click="pick(group.field, row.value)"
              >
                <td class="p-0">
                  <!-- The row's click handler takes the button's click too, so a key press works -->
                  <button :aria-pressed="filters[group.field] === row.value" class="block w-full px-3 py-2.5 text-left" type="button">{{ row.label }}</button>
                </td>

                <td class="px-3 py-2.5 text-right font-semibold tabular-nums">{{ row.count }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div
        v-else
        :aria-labelledby="`q-${group.field}`"
        class="flex flex-col gap-2"
        role="group"
      >
        <h3 :id="`q-${group.field}`" class="m-0 text-xs font-semibold uppercase tracking-wide text-surface-600">{{ group.label }}</h3>

        <div class="flex flex-wrap gap-1.5">
          <button
            :aria-pressed="filters[group.field] === null"
            class="inline-flex h-8 items-center gap-2 rounded-lg border-b-[3px] px-3 text-sm"
            :class="chip(filters[group.field] === null)"
            type="button"
            @click="pick(group.field, null)"
          >Any</button>

          <button
            v-for="option in group.options"
            :key="option.value"
            :aria-pressed="filters[group.field] === option.value"
            class="inline-flex h-8 items-center gap-2 rounded-lg border-b-[3px] px-3 text-sm"
            :class="chip(filters[group.field] === option.value)"
            type="button"
            @click="pick(group.field, option.value)"
          >{{ option.label }}<span class="inline-flex h-5 min-w-5 items-center justify-center rounded-md px-1.5 text-xs font-semibold tabular-nums" :class="badge(filters[group.field] === option.value)">{{ option.count }}</span></button>
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

  function chip (on: boolean): string {
    return on
      ? 'border-primary-600 font-medium text-primary-800 dark:border-primary-300 dark:text-primary-100'
      : 'border-transparent text-surface-900'
  }

  // No fill on a chip: the picked one has a coloured line under it. The count sits in a coloured badge, strong on the picked chip and soft on the others
  function badge (on: boolean): string {
    return on
      ? 'bg-primary-700 text-white dark:bg-primary-100 dark:text-primary-800'
      : 'bg-primary-100 text-primary-800 dark:bg-primary-800 dark:text-primary-100'
  }
</script>
