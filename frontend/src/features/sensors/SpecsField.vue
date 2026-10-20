<template>
  <fieldset class="m-0 flex min-w-0 flex-col gap-2 border-0 p-0">
    <legend class="mb-1 p-0 text-label text-surface-900">Specifications <span class="font-normal text-surface-600">(optional)</span></legend>

    <p class="m-0 text-xs text-surface-600">Shown on the model’s page, such as Operating range, Interface or Accuracy.</p>

    <ul v-if="specs.length > 0" class="m-0 flex list-none flex-col gap-2 p-0">
      <li v-for="(spec, index) in specs" :key="index" class="flex items-start gap-1.5 rounded-card bg-surface-50 p-2.5">
        <div class="grid min-w-0 grow grid-cols-1 gap-2 sm:grid-cols-2">
          <v-text-field
            v-model="spec.label"
            :aria-label="`Specification ${index + 1} name`"
            autocomplete="off"
            density="compact"
            hide-details
            maxlength="120"
            placeholder="Name, such as Accuracy"
          />

          <v-text-field
            v-model="spec.value"
            :aria-label="`Specification ${index + 1} value`"
            autocomplete="off"
            density="compact"
            hide-details
            maxlength="120"
            placeholder="Value, such as ±0.17 °C"
          />

          <v-text-field
            v-model="spec.detail"
            :aria-label="`Specification ${index + 1} second line`"
            autocomplete="off"
            class="sm:col-span-2"
            density="compact"
            hide-details
            maxlength="120"
            placeholder="Second line (optional)"
          />
        </div>

        <v-btn
          :aria-label="`Remove specification ${index + 1}`"
          icon
          size="36"
          variant="text"
          @click="remove(index)"
        >
          <v-icon :icon="mdiClose" size="18" />
        </v-btn>
      </li>
    </ul>

    <p v-if="error" class="m-0 text-sm text-error" role="alert">{{ error }}</p>

    <v-btn
      class="self-start"
      color="primary"
      :disabled="specs.length >= MODEL_MAX_SPECS"
      :prepend-icon="mdiPlus"
      variant="text"
      @click="add"
    >Add a specification</v-btn>
  </fieldset>
</template>

<script lang="ts" setup>
  import type { SpecValues } from './sensorForms'
  import { mdiClose, mdiPlus } from '@mdi/js'
  import { MODEL_MAX_SPECS } from './sensorForms'

  // The lines of a model's technical specifications, typed as text (SEN-1). A line needs both a
  // name and a value; half-typed ones are not saved.
  defineProps<{
    error?: string
  }>()

  const specs = defineModel<SpecValues[]>({ required: true })

  function add (): void {
    specs.value = [...specs.value, { label: '', value: '', detail: '' }]
  }

  function remove (index: number): void {
    specs.value = specs.value.filter((_, i) => i !== index)
  }
</script>
