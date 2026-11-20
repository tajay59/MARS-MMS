<template>
  <Transition :css="false" @enter="enter" @leave="leave">
    <slot />
  </Transition>
</template>

<script lang="ts" setup>
  import { dur, DURATION, EASE, gsap } from '@/app/motion'

  // A block that folds and unfolds (v-if or v-show on one child): its height eases open on Material's
  // emphasized curve, as the requests filter table does, and closes a little faster. Instant under
  // reduced motion. The content is never hidden by the animation: it only clips while it runs.
  function enter (el: Element, done: () => void): void {
    gsap.fromTo(el, { height: 0, opacity: 0, overflow: 'hidden' }, {
      height: 'auto',
      opacity: 1,
      duration: dur(DURATION.height),
      ease: EASE.emphasized,
      clearProps: 'height,opacity,overflow',
      onComplete: done,
    })
  }

  function leave (el: Element, done: () => void): void {
    gsap.to(el, {
      height: 0,
      opacity: 0,
      overflow: 'hidden',
      duration: dur(DURATION.height * 0.7),
      ease: EASE.emphasized,
      onComplete: done,
    })
  }
</script>
