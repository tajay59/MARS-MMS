<template>
  <button
    ref="button"
    :aria-pressed="active"
    class="inline-flex h-8 items-center gap-2 rounded-lg px-3 text-sm font-medium"
    :class="active ? 'text-primary-800 dark:text-primary-100' : 'text-surface-900'"
    type="button"
  >
    <!-- The picked chip's mark: a solid core with a lighter halo that pulses outward -->
    <span aria-hidden="true" class="relative grid size-2.5 shrink-0 place-items-center">
      <span ref="halo" class="absolute inset-0 rounded-full bg-primary-300 dark:bg-primary-500" />
      <span ref="dot" class="relative size-2.5 rounded-full bg-primary-700 dark:bg-primary-200" />
    </span>
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
  import { nextTick, onBeforeUnmount, onMounted, useTemplateRef, watch } from 'vue'
  import { dur, DURATION, EASE, gsap, reducedMotion } from '@/app/motion'

  // One filter chip (queue filters). The picked chip shows a two-tone circle at its left: a solid
  // core that grows in, and a lighter halo that pulses outward. Picking or letting go also eases the
  // colours of the text and the count. The new look is plain classes: the colour tween starts from
  // how the chip looked a moment before (read while the old classes are still there) and runs to the
  // new look, so there is nothing to keep in step by hand.
  // The pulse is the one thing here that loops, so it stops under reduced motion (WCAG 2.3.3) and
  // the halo is then a still ring.
  const props = defineProps<{ label: string, active: boolean, count?: number }>()

  const button = useTemplateRef<HTMLElement>('button')
  const halo = useTemplateRef<HTMLElement>('halo')
  const dot = useTemplateRef<HTMLElement>('dot')
  const badge = useTemplateRef<HTMLElement>('badge')

  const PULSE_S = 1.6
  const STILL_RING = { scale: 1.9, opacity: 0.4 }
  let pulse: gsap.core.Tween | null = null

  function stopPulse (): void {
    pulse?.kill()
    pulse = null
  }

  function show (animate: boolean): void {
    stopPulse()
    if (!dot.value || !halo.value) {
      return
    }
    const time = animate ? dur(DURATION.chip) : 0
    gsap.fromTo(dot.value, { scale: 0 }, { scale: 1, duration: time, ease: EASE.emphasized })
    if (reducedMotion()) {
      gsap.set(halo.value, STILL_RING)
      return
    }
    pulse = gsap.fromTo(
      halo.value,
      { scale: 1, opacity: 0.55 },
      { scale: 2.6, opacity: 0, duration: PULSE_S, ease: EASE.out, repeat: -1, repeatDelay: 0.15 },
    )
  }

  function hide (animate: boolean): void {
    stopPulse()
    if (!dot.value || !halo.value) {
      return
    }
    gsap.to(halo.value, { opacity: 0, duration: animate ? dur(DURATION.hover) : 0, ease: EASE.out })
    gsap.to(dot.value, { scale: 0, duration: animate ? dur(DURATION.chip) : 0, ease: EASE.emphasized })
  }

  onMounted(() => {
    if (props.active) {
      show(false)
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
      show(true)
    } else {
      hide(true)
    }
  }, { flush: 'pre' })
</script>
