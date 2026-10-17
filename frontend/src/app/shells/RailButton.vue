<template>
  <!--
    The tooltip is the link's sibling, not inside it: its visible text would otherwise be missing
    from the link's accessible name while it shows (WCAG 2.5.3). RailTip listens on this wrapper.
  -->
  <span class="relative z-1 flex" :data-active="active ? 'true' : undefined" data-rail-button>
    <router-link v-slot="{ href, navigate }" custom :to="to">
      <a
        :aria-current="active ? 'true' : undefined"
        :aria-describedby="hintId"
        :aria-label="badge ? `${label}, ${badge}` : label"
        class="relative flex size-11 shrink-0 items-center justify-center rounded-xl"
        :class="active ? 'text-primary-700 dark:text-primary-100' : 'text-surface-600 hover:text-surface-900'"
        :href="href"
        @click="navigate"
        @mouseenter="hover(true)"
        @mouseleave="hover(false)"
        @pointercancel="press(false)"
        @pointerdown="press(true)"
        @pointerup="press(false)"
      >
        <!-- The hover fill grows from the icon; the active fill is the rail's sliding indicator -->
        <span ref="halo" aria-hidden="true" class="absolute inset-0 rounded-xl bg-surface-100 opacity-0" />

        <span ref="glyph" class="relative flex">
          <v-icon :icon="icon" size="22" />
        </span>

        <span v-if="badge" aria-hidden="true" class="absolute right-2 top-2 size-2 rounded-full bg-primary ring-2 ring-surface" />
      </a>
    </router-link>

    <!-- The rail never expands: this names the section and what it holds, on hover and on focus -->
    <RailTip :hint="badge ? `${hint} · ${badge}` : hint" :hint-id="hintId" :label="label" />
  </span>
</template>

<script lang="ts" setup>
  import type { RouteLocationRaw } from 'vue-router'
  import { onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'
  import { dur, DURATION, EASE, gsap } from '@/app/motion'
  import RailTip from './RailTip.vue'

  const props = defineProps<{
    label: string
    hint: string
    icon: string
    to: RouteLocationRaw
    active?: boolean
    /** Something waits in the section, for example "2 waiting": a dot on the icon. */
    badge?: string | null
  }>()

  const hintId = useId()
  const halo = ref<HTMLElement | null>(null)
  const glyph = ref<HTMLElement | null>(null)
  let hovered = false

  // Hover (W4-10): the icon lifts and grows a little with a soft overshoot; the fill grows out
  // from it. The active section already has the indicator, so it gets no fill.
  function hover (on: boolean): void {
    hovered = on
    gsap.to(glyph.value, {
      scale: on ? 1.14 : 1,
      y: on ? -1 : 0,
      duration: dur(on ? 0.22 : DURATION.hover),
      ease: on ? EASE.pop : EASE.out,
    })
    gsap.to(halo.value, {
      opacity: on && !props.active ? 1 : 0,
      scale: on ? 1 : 0.7,
      duration: dur(DURATION.hover),
    })
  }

  function press (down: boolean): void {
    gsap.to(glyph.value, {
      scale: down ? 0.9 : (hovered ? 1.14 : 1),
      duration: dur(down ? 0.08 : 0.2),
      ease: down ? 'power1.out' : EASE.pop,
    })
  }

  // Becoming active under the pointer: the indicator takes over from the hover fill
  watch(() => props.active, active => {
    if (active) {
      gsap.to(halo.value, { opacity: 0, duration: dur(DURATION.hover) })
    }
  })

  onMounted(() => {
    gsap.set(halo.value, { scale: 0.7 })
  })

  onBeforeUnmount(() => {
    gsap.killTweensOf([halo.value, glyph.value])
  })
</script>
