<template>
  <button
    ref="button"
    :aria-pressed="active"
    class="relative inline-flex h-8 items-center gap-2 rounded-lg px-3 text-sm font-medium"
    :class="active ? 'text-primary-800 dark:text-primary-100' : 'text-surface-900'"
    type="button"
  >
    <!-- The line under the picked chip: a bottom border that curves up at its ends -->
    <span
      ref="line"
      aria-hidden="true"
      class="pointer-events-none absolute inset-0 rounded-lg border-b-[3px] border-primary-600 dark:border-primary-300"
      :class="active ? 'opacity-100' : 'opacity-0'"
    />
    {{ label }}
    <span
      v-if="count !== undefined"
      ref="badge"
      class="inline-flex h-5 min-w-5 items-center justify-center rounded-md px-1.5 text-xs font-semibold tabular-nums"
      :class="active ? 'bg-primary-700 text-white dark:bg-primary-100 dark:text-primary-800' : 'bg-primary-100 text-primary-800 dark:bg-primary-800 dark:text-primary-100'"
    >{{ count }}</span>
  </button>
</template>

<script lang="ts" setup>
  import { nextTick, useTemplateRef, watch } from 'vue'
  import { dur, DURATION, EASE, gsap } from '@/app/motion'

  // One filter chip (queue filters). Picking it fades and widens the line under it and eases the
  // colours of its text and count; letting go does the reverse. The new look is plain classes: the
  // tween starts from how the chip looked a moment before (read while the old classes are still
  // there) and runs to the new look, so there is nothing to keep in step by hand.
  const props = defineProps<{ label: string, active: boolean, count?: number }>()

  const button = useTemplateRef<HTMLElement>('button')
  const line = useTemplateRef<HTMLElement>('line')
  const badge = useTemplateRef<HTMLElement>('badge')

  const LINE_FROM = 0.4

  watch(() => props.active, async (now, was) => {
    // Still the old classes here: remember the colours before Vue changes them
    const before = {
      color: button.value ? getComputedStyle(button.value).color : '',
      badgeBg: badge.value ? getComputedStyle(badge.value).backgroundColor : '',
      badgeColor: badge.value ? getComputedStyle(badge.value).color : '',
    }
    await nextTick()
    const time = dur(DURATION.chip)
    if (button.value && before.color) {
      gsap.from(button.value, { color: before.color, duration: time, ease: EASE.decelerate, clearProps: 'color' })
    }
    if (badge.value && before.badgeBg) {
      gsap.from(badge.value, {
        backgroundColor: before.badgeBg, color: before.badgeColor, duration: time, ease: EASE.decelerate,
        clearProps: 'backgroundColor,color',
      })
    }
    if (line.value) {
      gsap.fromTo(
        line.value,
        { opacity: was ? 1 : 0, scaleX: was ? 1 : LINE_FROM },
        {
          opacity: now ? 1 : 0, scaleX: now ? 1 : LINE_FROM, duration: time,
          ease: now ? EASE.emphasized : EASE.out, clearProps: 'opacity,transform',
        },
      )
    }
  }, { flush: 'pre' })
</script>
