<template>
  <button
    ref="button"
    :aria-pressed="active"
    class="inline-flex h-8 items-center gap-2 rounded-lg px-3 text-sm font-medium"
    :class="active ? 'text-primary-800 dark:text-primary-100' : 'text-surface-900'"
    type="button"
  >
    {{ label }}
    <!-- The count. On the picked chip a lighter halo pulses outward behind its solid core -->
    <span v-if="count !== undefined" class="relative inline-flex">
      <span ref="halo" aria-hidden="true" class="absolute inset-0 rounded-md bg-primary-300 opacity-0 dark:bg-primary-500" />

      <span
        ref="badge"
        class="relative inline-flex h-5 min-w-5 items-center justify-center rounded-md px-1.5 text-xs font-semibold tabular-nums"
        :class="active ? 'bg-primary-700 text-white dark:bg-primary-100 dark:text-primary-800' : 'bg-primary-100 text-primary-800 dark:bg-primary-800 dark:text-primary-100'"
      >{{ count }}</span>
    </span>
  </button>
</template>

<script lang="ts" setup>
  import { nextTick, onBeforeUnmount, onMounted, useTemplateRef, watch } from 'vue'
  import { dur, DURATION, EASE, gsap, reducedMotion } from '@/app/motion'

  // One filter chip (queue filters). The picked chip's count is two-tone: a solid core, and a lighter
  // halo behind it that pulses outward. Picking or letting go also eases the colours of the text and
  // the count. The new look is plain classes: the colour tween starts from how the chip looked a
  // moment before (read while the old classes are still there) and runs to the new look, so there is
  // nothing to keep in step by hand.
  // The pulse is the one thing here that loops, so it stops under reduced motion (WCAG 2.3.3) and
  // the halo is then a still ring.
  const props = defineProps<{ label: string, active: boolean, count?: number }>()

  const button = useTemplateRef<HTMLElement>('button')
  const halo = useTemplateRef<HTMLElement>('halo')
  const badge = useTemplateRef<HTMLElement>('badge')

  const PULSE_S = 1.6
  const STILL_RING = { scale: 1.45, opacity: 0.45 }
  let pulse: gsap.core.Tween | null = null

  function stopPulse (): void {
    pulse?.kill()
    pulse = null
  }

  function show (): void {
    stopPulse()
    if (!halo.value) {
      return
    }
    if (reducedMotion()) {
      gsap.set(halo.value, STILL_RING)
      return
    }
    pulse = gsap.fromTo(
      halo.value,
      { scale: 1, opacity: 0.6 },
      { scale: 1.9, opacity: 0, duration: PULSE_S, ease: EASE.out, repeat: -1, repeatDelay: 0.15 },
    )
  }

  function hide (animate: boolean): void {
    stopPulse()
    if (halo.value) {
      gsap.to(halo.value, { opacity: 0, scale: 1, duration: animate ? dur(DURATION.hover) : 0, ease: EASE.out })
    }
  }

  onMounted(() => {
    if (props.active) {
      show()
    } else {
      hide(false)
    }
  })

  onBeforeUnmount(stopPulse)

  watch(() => props.active, async now => {
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
    if (now) {
      show()
    } else {
      hide(true)
    }
  }, { flush: 'pre' })
</script>
