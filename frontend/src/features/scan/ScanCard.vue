<template>
  <section
    :aria-labelledby="headingId"
    class="mx-auto flex w-full max-w-md flex-col items-center gap-3 rounded-card bg-surface-50 px-5 pb-4 pt-6 text-center"
  >
    <!-- The disc says what kind of message this is: grey for no signal, amber for an old label, red for an unknown code -->
    <span class="relative grid size-18 place-items-center rounded-full" :class="discClass[tone]">
      <span v-if="busy" aria-hidden="true" class="absolute -inset-1.25 animate-spin rounded-full border-[3px] border-transparent border-r-primary border-t-primary motion-reduce:animate-none" />
      <v-icon :icon="icon" size="32" />
    </span>

    <h2 :id="headingId" class="m-0 text-h2 text-surface-900 text-balance">{{ title }}</h2>
    <p v-if="$slots.default" class="m-0 text-pretty text-surface-600"><slot /></p>

    <div v-if="$slots.actions" class="mt-1 flex w-full flex-col gap-2">
      <slot name="actions" />
    </div>
  </section>
</template>

<script lang="ts" setup>
  import { useId } from 'vue'

  // One layout for every state of the scanner and of a scanned page (AFD §5.3): an icon disc, a
  // title, one sentence and the actions. `busy` draws a ring that turns (still under reduced motion).
  defineProps<{
    icon: string
    title: string
    tone: 'primary' | 'neutral' | 'warning' | 'error'
    busy?: boolean
  }>()

  const headingId = useId()

  const discClass = {
    primary: 'bg-primary-50 text-primary',
    neutral: 'bg-surface-100 text-surface-600',
    warning: 'bg-warning-container text-on-warning-container',
    error: 'bg-error-container text-on-error-container',
  } as const
</script>
