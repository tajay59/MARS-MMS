<template>
  <section aria-labelledby="specs-h">
    <div class="mb-2.5 flex flex-wrap items-center justify-between gap-2">
      <h2 id="specs-h" class="m-0 text-h3 text-surface-900">Specifications</h2>

      <v-btn
        v-if="canWrite && model.specs.length === 0"
        color="primary"
        :prepend-icon="mdiPencilOutline"
        variant="text"
        @click="$emit('edit')"
      >Add specifications</v-btn>
    </div>

    <dl class="m-0 grid grid-cols-2 gap-2 md:grid-cols-4">
      <div v-for="cell in cells" :key="cell.label" class="flex min-w-0 flex-col gap-0.5 rounded-card bg-surface-50 px-3.5 py-3">
        <dt class="text-xs uppercase tracking-wide text-surface-600">{{ cell.label }}</dt>
        <dd class="m-0 truncate text-sm font-semibold text-surface-900">{{ cell.value }}</dd>
        <dd v-if="cell.detail" class="m-0 truncate font-mono text-xs text-surface-600" translate="no">{{ cell.detail }}</dd>
      </div>
    </dl>
  </section>
</template>

<script lang="ts" setup>
  import type { SensorModelOut } from '@/api/models'
  import { mdiPencilOutline } from '@mdi/js'
  import { computed } from 'vue'

  // The model's make, its technical specifications and its calibration interval, as one strip.
  // Specifications are free text a person entered (SEN-1): loggers and sensors have different ones.
  const props = defineProps<{
    model: SensorModelOut
    canWrite: boolean
  }>()

  defineEmits<{
    edit: []
  }>()

  const cells = computed(() => {
    const list: { label: string, value: string, detail?: string | null }[] = [
      { label: 'Make', value: props.model.manufacturer },
      ...props.model.specs.map(s => ({ label: s.label, value: s.value, detail: s.detail })),
    ]
    const days = props.model.default_calibration_interval_days
    if (days) {
      list.push({ label: 'Calibrate every', value: `${days} days` })
    }
    return list
  })
</script>
