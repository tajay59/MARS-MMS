<template>
  <div class="flex flex-col gap-4">
    <FormField id="due-within" label="Due within">
      <v-select
        id="due-within"
        item-title="title"
        item-value="value"
        :items="windows"
        :model-value="filters.within"
        @update:model-value="emit('change', { within: $event })"
      />
    </FormField>

    <FormField id="due-org" label="Organization">
      <v-select
        id="due-org"
        clearable
        item-title="title"
        item-value="value"
        :items="orgs"
        :model-value="filters.org"
        placeholder="All organizations"
        @update:model-value="emit('change', { org: $event ?? null })"
      />
    </FormField>

    <FormField id="due-country" label="Country">
      <v-select
        id="due-country"
        clearable
        item-title="title"
        item-value="value"
        :items="countries"
        :model-value="filters.country"
        placeholder="All countries"
        @update:model-value="emit('change', { country: $event ?? null })"
      />
    </FormField>
  </div>
</template>

<script lang="ts" setup>
  import type { DueFilters } from './calibration'
  import FormField from '@/components/FormField.vue'

  // The calibration list's filters: how far ahead, whose and where. In the pane from 768 px, in a
  // bottom sheet on phones.
  defineProps<{
    filters: DueFilters
    windows: { value: number, title: string }[]
    orgs: { value: string, title: string }[]
    countries: { value: string, title: string }[]
  }>()

  const emit = defineEmits<{ change: [patch: Partial<DueFilters>] }>()
</script>
