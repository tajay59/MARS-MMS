<template>
  <!--
    A rail tooltip, shown while its parent is hovered or has keyboard focus, and hidden again with
    Escape (WCAG 1.4.13). GSAP fades and slides it out from the rail (W4-10). Screen readers get
    the hint from the parent's aria-describedby, so this stays aria-hidden.
  -->
  <span
    ref="tip"
    aria-hidden="true"
    class="pointer-events-none invisible absolute left-full top-1/2 z-[1006] ml-3 flex -translate-y-1/2 flex-col gap-0.5 whitespace-nowrap rounded-md bg-surface-900 px-3 py-2 text-left text-surface-0 opacity-0 shadow-lg"
  >
    <span class="text-sm font-semibold leading-4">{{ label }}</span>
    <span :id="hintId" class="text-xs leading-4">{{ hint }}</span>
  </span>
</template>

<script lang="ts" setup>
  import { onBeforeUnmount, onMounted, ref } from 'vue'
  import { dur, DURATION, EASE, gsap } from '@/app/motion'

  defineProps<{ label: string, hint: string, hintId: string }>()

  const tip = ref<HTMLElement | null>(null)
  let host: HTMLElement | null = null
  let hovered = false
  let focused = false

  // overwrite: true kills the other tween at once. The global 'auto' only resolves conflicts when a
  // tween first renders, so a hide during show's delay was itself killed when show started, and a
  // quick sweep down the rail left tips stuck open.
  function show (): void {
    gsap.fromTo(tip.value, { autoAlpha: 0, x: -6, scale: 0.96 }, {
      autoAlpha: 1, x: 0, scale: 1, duration: dur(DURATION.tip), delay: dur(0.05), ease: EASE.out,
      transformOrigin: 'left center', overwrite: true,
    })
  }

  function hide (): void {
    gsap.to(tip.value, { autoAlpha: 0, x: -4, duration: dur(0.1), ease: 'power1.in', overwrite: true })
  }

  function update (wasShown: boolean): void {
    const shown = hovered || focused
    if (shown !== wasShown) {
      if (shown) {
        show()
      } else {
        hide()
      }
    }
  }

  function on (change: () => void): () => void {
    return () => {
      const was = hovered || focused
      change()
      update(was)
    }
  }

  const handlers: Record<string, (event: Event) => void> = {
    mouseenter: on(() => {
      hovered = true
    }),
    mouseleave: on(() => {
      hovered = false
    }),
    // Keyboard focus only: a click's focus doesn't open it
    focusin: on(() => {
      focused = Boolean(host?.matches(':has(:focus-visible), :focus-visible'))
    }),
    focusout: on(() => {
      focused = false
    }),
    pointerdown: on(() => {
      hovered = false
      focused = false
    }),
    keydown: event => {
      if ((event as KeyboardEvent).key === 'Escape') {
        on(() => {
          hovered = false
          focused = false
        })()
      }
    },
  }

  onMounted(() => {
    host = tip.value?.parentElement ?? null
    for (const [name, handler] of Object.entries(handlers)) {
      host?.addEventListener(name, handler)
    }
  })

  onBeforeUnmount(() => {
    for (const [name, handler] of Object.entries(handlers)) {
      host?.removeEventListener(name, handler)
    }
    gsap.killTweensOf(tip.value)
  })
</script>
