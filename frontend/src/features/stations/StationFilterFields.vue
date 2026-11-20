<template>
  <div class="flex flex-col gap-4">
    <!-- Organization (staff), country and type: labelled fields in the sheet; in the pane the label sits inside -->
    <template v-for="field in selects" :key="field.key">
      <v-select
        v-if="inline"
        clearable
        hide-details
        :items="field.items"
        :label="field.label"
        :model-value="filters[field.key]"
        :no-data-text="field.empty"
        single-line
        @update:model-value="emit('change', { [field.key]: $event ?? null })"
      />

      <FormField v-else :id="`${uid}-${field.key}`" :label="field.label">
        <v-select
          :id="`${uid}-${field.key}`"
          clearable
          hide-details
          :items="field.items"
          :model-value="filters[field.key]"
          :no-data-text="field.empty"
          :placeholder="field.placeholder"
          @update:model-value="emit('change', { [field.key]: $event ?? null })"
        />
      </FormField>
    </template>

    <div v-if="facets.parameters.length > 0" :aria-labelledby="`${uid}-measures`" class="flex flex-col gap-2" role="group">
      <span :id="`${uid}-measures`" class="text-label text-surface-900">Measures</span>

      <span v-if="measures.common.length > 0" class="flex flex-wrap gap-1.5">
        <button
          v-for="p in measures.common"
          :key="p"
          :aria-pressed="filters.parameter === p"
          class="inline-flex h-7 items-center rounded-full border px-2.5 font-mono text-xs font-medium"
          :class="filters.parameter === p ? 'border-transparent bg-primary-100 text-primary-700 dark:bg-primary-800 dark:text-primary-100' : 'border-surface-300 text-surface-700 hover:bg-surface-100'"
          type="button"
          @click="emit('change', { parameter: filters.parameter === p ? null : p })"
        >{{ p }}</button>
      </span>

      <!-- The rest, searchable: the real stations measure about a hundred (W5-8) -->
      <v-autocomplete
        v-if="measures.other.length > 0"
        :aria-label="measures.common.length > 0 ? 'Other measures' : 'Measures'"
        auto-select-first
        clearable
        hide-details
        :items="measures.other"
        :model-value="otherSelected"
        no-data-text="No measure matches"
        :placeholder="measures.common.length > 0 ? 'Other measures' : 'All measures'"
        @update:model-value="emit('change', { parameter: $event ?? null })"
      />
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
  import { extraFilterCount, splitParameters } from './stations'

  // Organization (staff only), country, type and measures: in the pane, or the phone's sheet
  const props = defineProps<{
    filters: StationFilters
    facets: { orgs: { value: string, title: string }[], countries: string[], types: string[], parameters: string[] }
    showOrg: boolean
    /** In the pane: each select's label sits inside it (approved "Stations pane filters"). */
    inline?: boolean
  }>()
  const emit = defineEmits<{ change: [patch: Partial<StationFilters>] }>()

  const uid = useId()
  const countryItems = computed(() => props.facets.countries.map(code => ({ value: code, title: countryName(code) })))
  const selects = computed(() => [
    ...(props.showOrg ? [{ key: 'org' as const, label: 'Organization', placeholder: 'All organizations', items: props.facets.orgs, empty: 'No organizations' }] : []),
    { key: 'country' as const, label: 'Country', placeholder: 'All countries', items: countryItems.value, empty: 'No countries' },
    { key: 'type' as const, label: 'Type', placeholder: 'All types', items: props.facets.types, empty: 'No types recorded' },
  ])
  const active = computed(() => extraFilterCount(props.filters) > 0)
  const measures = computed(() => splitParameters(props.facets.parameters))
  /** The field shows the chosen measure only when it is one of the others (a chip shows its own). */
  const otherSelected = computed(() => {
    const p = props.filters.parameter
    return p && measures.value.other.includes(p) ? p : null
  })
</script>
