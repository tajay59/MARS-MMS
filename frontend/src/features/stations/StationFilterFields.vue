<template>
  <div class="flex flex-col gap-4">
    <FormField v-if="showOrg" :id="`${uid}-org`" label="Organization">
      <v-select
        :id="`${uid}-org`"
        clearable
        hide-details
        :items="facets.orgs"
        :model-value="filters.org"
        placeholder="All organizations"
        @update:model-value="emit('change', { org: $event ?? null })"
      />
    </FormField>

    <FormField :id="`${uid}-country`" label="Country">
      <v-select
        :id="`${uid}-country`"
        clearable
        hide-details
        :items="countryItems"
        :model-value="filters.country"
        placeholder="All countries"
        @update:model-value="emit('change', { country: $event ?? null })"
      />
    </FormField>

    <FormField :id="`${uid}-type`" label="Type">
      <v-select
        :id="`${uid}-type`"
        clearable
        hide-details
        :items="facets.types"
        :model-value="filters.type"
        no-data-text="No types recorded"
        placeholder="All types"
        @update:model-value="emit('change', { type: $event ?? null })"
      />
    </FormField>

    <div v-if="facets.parameters.length > 0" :aria-labelledby="`${uid}-measures`" class="flex flex-col gap-2" role="group">
      <span :id="`${uid}-measures`" class="text-label text-surface-900">Measures</span>

      <span class="flex flex-wrap gap-1.5">
        <button
          v-for="p in facets.parameters"
          :key="p"
          :aria-pressed="filters.parameter === p"
          class="inline-flex h-7 items-center rounded-full border px-2.5 font-mono text-xs font-medium"
          :class="filters.parameter === p ? 'border-transparent bg-primary-100 text-primary-700 dark:bg-primary-800 dark:text-primary-100' : 'border-surface-300 text-surface-700 hover:bg-surface-100'"
          type="button"
          @click="emit('change', { parameter: filters.parameter === p ? null : p })"
        >{{ p }}</button>
      </span>
    </div>

    <button
      v-if="active"
      class="self-start rounded-md px-2 py-1.5 text-sm font-medium text-primary hover:bg-surface-100"
      type="button"
      @click="emit('change', { org: null, country: null, type: null, parameter: null })"
    >Clear these filters</button>
  </div>
</template>

<script lang="ts" setup>
  import type { StationFilters } from './stations'
  import { computed, useId } from 'vue'
  import { countryName } from '@/app/countries'
  import FormField from '@/components/FormField.vue'
  import { extraFilterCount } from './stations'

  // Organization (staff only), country, type and measures: in the pane, or the phone's sheet
  const props = defineProps<{
    filters: StationFilters
    facets: { orgs: { value: string, title: string }[], countries: string[], types: string[], parameters: string[] }
    showOrg: boolean
  }>()
  const emit = defineEmits<{ change: [patch: Partial<StationFilters>] }>()

  const uid = useId()
  const countryItems = computed(() => props.facets.countries.map(code => ({ value: code, title: countryName(code) })))
  const active = computed(() => extraFilterCount(props.filters) > 0)
</script>
