<template>
  <!-- The field shell has its own top bar: the page is just its content there -->
  <div v-if="inField" class="flex grow flex-col">
    <slot />
  </div>

  <template v-else>
    <!-- The view tile's header: the page or record, and its actions (DBD "The app shell") -->
    <header class="flex min-h-18 shrink-0 flex-wrap items-center gap-x-3 gap-y-2 border-b border-surface-200 py-3 pl-4 pr-4 md:pl-6">
      <v-btn
        v-if="back && !mdAndUp"
        :aria-label="backLabel"
        class="-ml-2"
        icon
        size="40"
        :to="back"
        variant="text"
      >
        <v-icon class="text-surface-700" :icon="mdiArrowLeft" />
      </v-btn>

      <v-btn
        v-if="pane?.canExpand.value"
        aria-label="Show the list"
        class="-ml-2"
        icon
        size="36"
        variant="text"
        @click="pane.toggle()"
      >
        <v-icon class="text-surface-600" :icon="mdiDockLeft" size="20" />
      </v-btn>

      <div ref="titleEl" class="min-w-0 grow basis-48">
        <h1 :id="headingId" class="m-0 wrap-break-word text-h2 text-surface-900">{{ heading }}</h1>
        <!-- A record's facts under its name (code, status chip, place) -->
        <div v-if="$slots.subtitle" class="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-sm text-surface-600">
          <slot name="subtitle" />
        </div>

        <p v-else-if="subtitle" class="m-0 text-sm text-surface-600">{{ subtitle }}</p>
      </div>

      <div v-if="$slots.actions" class="flex shrink-0 flex-wrap items-center gap-2">
        <slot name="actions" />
      </div>
    </header>

    <!-- Focusable, so keyboard users can scroll it even when nothing inside takes focus (WCAG 2.1.1) -->
    <div
      ref="regionEl"
      :aria-labelledby="headingId"
      class="grow md:min-h-0 md:overflow-y-auto"
      role="region"
      tabindex="0"
    >
      <div ref="contentEl" class="w-full p-4 md:px-8 md:py-7" :class="wide ? '' : 'max-w-270'">
        <slot />
      </div>
    </div>
  </template>
</template>

<script lang="ts" setup>
  import type { RouteLocationRaw } from 'vue-router'
  import { mdiArrowLeft, mdiDockLeft } from '@mdi/js'
  import { computed, inject, ref, useId, watch } from 'vue'
  import { useRoute } from 'vue-router'
  import { useDisplay } from 'vuetify'
  import { dur, DURATION, EASE, gsap } from '@/app/motion'
  import { shellKey, usePane } from '@/app/shells/pane'

  const props = defineProps<{
    /** The h1; the route's title when absent. */
    title?: string
    subtitle?: string
    /** Phones: where Back goes when a record is open (the list). */
    back?: RouteLocationRaw
    backLabel?: string
    /** Use the whole width of the view (tables, maps). */
    wide?: boolean
    /** The record open in the view (its id): when it changes, the new one rises in. */
    record?: string | null
  }>()

  const route = useRoute()
  const { mdAndUp } = useDisplay()
  const pane = usePane()
  const inField = inject(shellKey, 'app') === 'field'
  const headingId = useId()
  const heading = computed(() => props.title ?? String(route.meta.title ?? ''))
  const backLabel = computed(() => props.backLabel ?? 'Back to the list')

  // Another record from the pane (or back to the summary): the title and body rise in as a page
  // does (W4-10), from the top of the view. Phones already slide the view in from the side.
  const titleEl = ref<HTMLElement | null>(null)
  const regionEl = ref<HTMLElement | null>(null)
  const contentEl = ref<HTMLElement | null>(null)
  watch(() => props.record, () => {
    if (regionEl.value) {
      regionEl.value.scrollTop = 0
    }
    if (!mdAndUp.value || !titleEl.value || !contentEl.value) {
      return
    }
    gsap.fromTo([titleEl.value, contentEl.value], { autoAlpha: 0, y: 14 }, {
      autoAlpha: 1,
      y: 0,
      duration: dur(DURATION.record),
      ease: EASE.decelerate,
      stagger: dur(0.08),
      clearProps: 'transform,opacity,visibility',
    })
  }, { flush: 'post' })
</script>
