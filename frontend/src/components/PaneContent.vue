<template>
  <Teleport v-if="pane?.target.value" :to="pane.target.value">
    <div ref="root" class="flex flex-col">
      <slot />
    </div>
  </Teleport>
</template>

<script lang="ts" setup>
  import { onBeforeUnmount, ref, watch } from 'vue'
  import { dur, DURATION, gsap } from '@/app/motion'
  import { usePane } from '@/app/shells/pane'

  // The page's list or controls, shown in the shell's interactive pane (DBD "The app shell").
  // A new page's list slides in from the rail's side (W4-10).
  // `pin`: on phones the pane (title, tabs and this content) stays at the top while the page's list
  // scrolls up under a curved edge. Only for a short pane: a tall one would cover the screen.
  const props = defineProps<{ pin?: boolean }>()
  const pane = usePane()
  const root = ref<HTMLElement | null>(null)
  if (pane) {
    pane.blocks.value++
    watch(() => props.pin, pin => {
      pane.pinned.value = Boolean(pin)
    }, { immediate: true })
    onBeforeUnmount(() => {
      pane.blocks.value--
      pane.pinned.value = false
    })
  }

  const stop = watch(root, el => {
    if (el) {
      stop()
      gsap.fromTo(el, { autoAlpha: 0, x: -10 }, {
        autoAlpha: 1, x: 0, duration: dur(DURATION.page), clearProps: 'transform,opacity,visibility',
      })
    }
  })
</script>
