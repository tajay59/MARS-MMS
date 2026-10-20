<template>
  <div :aria-labelledby="labelledby" class="flex flex-wrap gap-1.5 md:gap-0" role="group">
    <button
      v-for="option in options"
      :key="option.value"
      :aria-pressed="model === option.value"
      class="inline-flex h-10 items-center gap-1.5 border px-4 text-sm font-medium max-md:rounded-full md:-ml-px md:first:ml-0 md:first:rounded-l-md md:last:rounded-r-md"
      :class="model === option.value
        ? 'relative z-1 border-primary bg-primary-100 text-primary-700 dark:bg-primary-800 dark:text-primary-100'
        : 'border-surface-500 text-surface-900 hover:bg-surface-100'"
      type="button"
      @click="model = option.value"
    >
      <v-icon v-if="model === option.value" :icon="mdiCheck" size="16" />{{ option.label }}
    </button>
  </div>
</template>

<script lang="ts" setup>
  import { mdiCheck } from '@mdi/js'

  // One choice from a few, as buttons that wrap on phones (DBD "New request": category and
  // priority). A group of toggle buttons: each says whether it is pressed.
  defineProps<{
    options: readonly { value: string, label: string }[]
    labelledby: string
  }>()

  const model = defineModel<string>({ required: true })
</script>
