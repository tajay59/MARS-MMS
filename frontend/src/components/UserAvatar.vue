<template>
  <!--
    A person's initials on a brand gradient (decision W4-13: the one place DBD allows a gradient).
    Decoration: the name is always written next to it, so it is hidden from screen readers.
    Both stops are tone 30-40 of the brand palettes, so white initials keep 4.5:1 in both themes.
  -->
  <span
    aria-hidden="true"
    class="inline-flex shrink-0 select-none items-center justify-center rounded-full bg-linear-135 font-semibold tracking-wide text-white"
    :class="[GRADIENTS[pick], SIZES[size ?? 'md']]"
  >{{ initials }}</span>
</template>

<script lang="ts" setup>
  import { computed } from 'vue'
  import { initialsOf, pickOf } from './avatar'

  const props = defineProps<{
    name: string
    /** Picks the gradient, so one person keeps theirs everywhere: their id. */
    seed: string
    size?: 'sm' | 'md' | 'lg'
  }>()

  // Written out in full so Tailwind finds each class
  const GRADIENTS = [
    'from-primary-600 to-tertiary-600',
    'from-tertiary-700 to-primary-600',
    'from-secondary-600 to-primary-700',
    'from-primary-700 to-secondary-600',
    'from-tertiary-600 to-secondary-700',
    'from-secondary-700 to-tertiary-600',
  ] as const

  const SIZES = { sm: 'size-10 text-sm', md: 'size-14 text-lg', lg: 'size-16 text-xl' } as const

  const initials = computed(() => initialsOf(props.name))
  const pick = computed(() => pickOf(props.seed, GRADIENTS.length))
</script>
