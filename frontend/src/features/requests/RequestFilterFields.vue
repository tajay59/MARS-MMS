<template>
  <div class="flex flex-col gap-4">
    <FormField v-if="showOrg" :id="`${uid}-org`" label="Organization">
      <v-select
        :id="`${uid}-org`"
        class="[&_.v-field]:bg-surface-50"
        clearable
        flat
        hide-details
        item-title="name"
        item-value="id"
        :items="facets.orgs"
        :model-value="filters.org"
        placeholder="All organizations"
        variant="solo-inverted"
        @update:model-value="emit('change', { org: $event ?? null })"
      />
    </FormField>

    <FormField :id="`${uid}-country`" label="Country">
      <v-select
        :id="`${uid}-country`"
        class="[&_.v-field]:bg-surface-50"
        clearable
        flat
        hide-details
        :items="countryItems"
        :model-value="filters.country"
        placeholder="All countries"
        variant="solo-inverted"
        @update:model-value="emit('change', { country: $event ?? null })"
      />
    </FormField>

    <FormField :id="`${uid}-category`" label="Category">
      <v-select
        :id="`${uid}-category`"
        class="[&_.v-field]:bg-surface-50"
        clearable
        flat
        hide-details
        item-title="label"
        item-value="value"
        :items="CATEGORIES"
        :model-value="filters.category"
        placeholder="All categories"
        variant="solo-inverted"
        @update:model-value="emit('change', { category: $event ?? null })"
      />
    </FormField>

    <FormField :id="`${uid}-priority`" label="Priority">
      <v-select
        :id="`${uid}-priority`"
        class="[&_.v-field]:bg-surface-50"
        clearable
        flat
        hide-details
        item-title="label"
        item-value="value"
        :items="PRIORITIES"
        :model-value="filters.priority"
        placeholder="Any priority"
        variant="solo-inverted"
        @update:model-value="emit('change', { priority: $event ?? null })"
      />
    </FormField>

    <FormField :id="`${uid}-created`" label="Created">
      <v-select
        :id="`${uid}-created`"
        class="[&_.v-field]:bg-surface-50"
        flat
        hide-details
        item-title="label"
        item-value="value"
        :items="CREATED_PRESETS"
        :model-value="filters.created"
        variant="solo-inverted"
        @update:model-value="emit('change', { created: $event ?? 'any' })"
      />
    </FormField>

    <button
      v-if="active"
      class="self-start rounded-md px-2 py-1.5 text-sm font-medium text-primary hover:bg-surface-100"
      type="button"
      @click="emit('change', { org: null, country: null, category: null, priority: null, created: 'any' })"
    >Clear these filters</button>
  </div>
</template>

<script lang="ts" setup>
  import type { RequestFilters } from './requests'
  import { computed, useId } from 'vue'
  import { countryName } from '@/app/countries'
  import FormField from '@/components/FormField.vue'
  import { CATEGORIES, CREATED_PRESETS, extraFilterCount, PRIORITIES } from './requests'

  // Organization (staff only), country, category, priority and date: in the pane, or the phone's sheet
  const props = defineProps<{
    filters: RequestFilters
    facets: { orgs: { id: string, name: string }[], countries: string[] }
    showOrg: boolean
  }>()
  const emit = defineEmits<{ change: [patch: Partial<RequestFilters>] }>()

  const uid = useId()
  const countryItems = computed(() => props.facets.countries.map(code => ({ value: code, title: countryName(code) })))
  const active = computed(() => extraFilterCount(props.filters) > 0)
</script>
