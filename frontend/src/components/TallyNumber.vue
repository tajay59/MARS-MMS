<template>
  <span class="tabular-nums">{{ shown }}</span>
</template>

<script lang="ts" setup>
  import { onBeforeUnmount, ref, watch } from 'vue'
  import { dur, gsap } from '@/app/motion'

  // A count that rolls to its new value when it changes (the Stations ledger re-tallying as search
  // and filters narrow it), so the change is seen, not just the result. Tabular figures keep the
  // width still while it rolls; under reduced motion it changes at once.
  const props = defineProps<{ value: number }>()

  const shown = ref(props.value)
  const state = { n: props.value }

  watch(() => props.value, to => {
    gsap.to(state, {
      n: to,
      duration: dur(0.3),
      ease: 'power2.out',
      overwrite: true,
      onUpdate: () => {
        shown.value = Math.round(state.n)
      },
      onComplete: () => {
        shown.value = to
      },
    })
  })

  onBeforeUnmount(() => gsap.killTweensOf(state))
</script>
