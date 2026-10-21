<template>
  <a class="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[2000] focus:rounded-md focus:bg-surface focus:px-4 focus:py-2" href="#main">
    Skip to main content
  </a>

  <!--
    The app shell for staff and clients (DBD "The app shell"): three square tiles on the ground
    colour, 5 px apart: the rail, the interactive pane (choose a page, a record, filters) and the
    view (the details). On phones the pane and view fill the screen; below 1024 px the rail is a bar docked to the bottom.
  -->
  <div
    ref="rootEl"
    class="flex h-dvh scroll-pb-[calc(84px+env(safe-area-inset-bottom))] flex-col overflow-y-auto bg-surface pb-[calc(84px+env(safe-area-inset-bottom))] pl-[env(safe-area-inset-left)] pr-[env(safe-area-inset-right)] pt-[env(safe-area-inset-top)] md:flex-row md:gap-[5px] md:overflow-hidden md:bg-ground md:p-[5px] md:pb-[calc(76px+env(safe-area-inset-bottom))] lg:pb-[5px]"
  >
    <AppRail v-if="lgAndUp" :badges="badges" :current="section" :sections="sections" />

    <!--
      The pane's resting widths are these classes; when it opens, closes or changes width, GSAP
      tweens its width and the view tile follows (decision W4-10). The inner block keeps the
      final width meanwhile, so the list doesn't reflow on every frame.
    -->
    <section
      v-show="paneOpen"
      ref="paneEl"
      aria-labelledby="pane-h"
      class="flex shrink-0 flex-col bg-surface md:min-h-0 md:w-[300px] lg:w-[360px] 2xl:w-[420px]"
      :class="stuck ? 'sticky top-[env(safe-area-inset-top)] z-10 bg-surface-50 md:static md:bg-surface' : ''"
    >
      <div ref="paneInner" class="flex min-h-0 grow flex-col">
        <!-- Phones: the bottom bar already says which section this is, so the title is for screen readers only -->
        <div class="flex min-h-14 shrink-0 items-center gap-1 pl-5 pr-3 pt-2 max-md:sr-only">
          <h2 id="pane-h" class="m-0 grow truncate text-h2 text-surface-900">{{ paneTitle }}</h2>

          <v-btn
            v-if="lgAndUp"
            aria-label="Hide the list"
            icon
            size="36"
            variant="text"
            @click="toggle"
          >
            <v-icon class="text-surface-600" :icon="mdiDockLeft" size="20" />
          </v-btn>
        </div>

        <nav v-if="tabs.length > 1" :aria-label="`${paneTitle} pages`" class="flex flex-wrap gap-1 px-4 pt-2 max-md:pt-3">
          <router-link
            v-for="tab in tabs"
            :key="tab.to"
            v-slot="{ href, navigate }"
            custom
            :to="{ name: tab.to }"
          >
            <a
              :aria-current="tab.current ? 'page' : undefined"
              class="inline-flex h-8 items-center gap-1.5 rounded-full px-3.5 text-sm font-medium"
              :class="tab.current
                ? 'bg-primary-100 text-primary-700 dark:bg-primary-800 dark:text-primary-100'
                : 'text-surface-600 hover:bg-surface-100 hover:text-surface-900'"
              :href="href"
              @click="navigate"
            >
              {{ tab.label }}
              <span v-if="tab.count" class="text-xs font-semibold tabular-nums">{{ tab.count }}<span class="sr-only"> waiting</span></span>
            </a>
          </router-link>
        </nav>

        <div
          ref="target"
          class="flex grow flex-col pb-4 md:min-h-0 md:overflow-y-auto"
          :class="[tabs.length > 1 ? 'pt-3' : 'pt-1', stuck ? 'max-md:pb-2' : '']"
        />
      </div>

    </section>

    <main
      id="main"
      ref="mainEl"
      class="flex min-w-0 grow flex-col bg-surface outline-none md:min-h-0 md:overflow-hidden"
      tabindex="-1"
    >
      <slot />
    </main>

    <AppTabBar v-if="!lgAndUp" :badges="badges" :current="section" :sections="sections" />
    <NotificationToast />
  </div>
</template>

<script lang="ts" setup>
  import { mdiDockLeft } from '@mdi/js'
  import { storeToRefs } from 'pinia'
  import { computed, nextTick, onBeforeUnmount, onMounted, provide, ref, watch } from 'vue'
  import { useRoute } from 'vue-router'
  import { useDisplay } from 'vuetify'
  import { dur, DURATION, EASE, gsap } from '@/app/motion'
  import { clientSections, sectionOf, sectionsFor, staffSections } from '@/app/navigation'
  import NotificationToast from '@/features/notifications/NotificationToast.vue'
  import { useNotificationsStore } from '@/stores/notifications'
  import { useRegistrationsStore } from '@/stores/registrations'
  import { useSessionStore } from '@/stores/session'
  import AppRail from './AppRail.vue'
  import AppTabBar from './AppTabBar.vue'
  import { paneKey, shellKey } from './pane'

  const COLLAPSED_KEY = 'mms.pane.collapsed'

  const { mdAndUp, lgAndUp, xxl } = useDisplay()
  const session = useSessionStore()
  const { isAdmin, isClient, roles } = storeToRefs(session)
  const registrations = useRegistrationsStore()
  // The live channel and the unread count run while the app shell is open (PRD NOT-1)
  const notifications = useNotificationsStore()
  onMounted(() => notifications.start())
  onBeforeUnmount(() => notifications.stop())
  const route = useRoute()

  const sections = computed(() => sectionsFor(isClient.value ? clientSections : staffSections, roles.value))
  const section = computed(() => sectionOf(sections.value, route.name))
  const paneTitle = computed(() => section.value?.label ?? 'Account')
  const badges = computed<Record<string, string | null>>(() => {
    const waiting = registrations.label()
    return { admin: waiting ? `${waiting} waiting` : null }
  })
  const tabs = computed(() => (section.value?.items ?? []).map(item => ({
    ...item,
    current: item.to === route.name || (typeof route.name === 'string' && item.also?.includes(route.name) === true),
    count: item.to === 'admin-registrations' ? registrations.label() : null,
  })))

  // The pane, shared with pages through usePane() and <PaneContent>
  const target = ref<HTMLElement | null>(null)
  const blocks = ref(0)
  const selected = ref(false)
  const pinned = ref(false)
  const rootEl = ref<HTMLElement | null>(null)
  // Phones only (the classes undo it from 768 px); the list is showing, not a record
  const stuck = computed(() => pinned.value && !selected.value)
  const collapsed = ref(readCollapsed())
  const hasPane = computed(() => tabs.value.length > 1 || blocks.value > 0)
  const canExpand = computed(() => hasPane.value && collapsed.value && lgAndUp.value)
  // Phones show the list, then the record alone once one is open
  const paneShown = computed(() => hasPane.value && (mdAndUp.value ? !(lgAndUp.value && collapsed.value) : !selected.value))

  // --- Tile motion (W4-10) ---------------------------------------------------------------------
  // Keep in step with the section's width classes: md 300, lg 360, 2xl 420
  const GAP = 5
  const restingWidth = computed(() => xxl.value ? 420 : (lgAndUp.value ? 360 : 300))
  const paneEl = ref<HTMLElement | null>(null)
  const paneInner = ref<HTMLElement | null>(null)
  const mainEl = ref<HTMLElement | null>(null)
  /** The pane is in the layout: true while it shows, and while it animates closed. */
  const paneOpen = ref(paneShown.value)
  let tween: gsap.core.Tween | null = null

  /** Tweens the pane from its current width to `width` (0 = closed); the view fills the rest. */
  function tweenPane (width: number, done?: () => void): void {
    const pane = paneEl.value
    const inner = paneInner.value
    if (!pane || !inner) {
      // Not mounted yet (the first page's list arrives while the shell renders): no motion
      paneOpen.value = width > 0
      done?.()
      return
    }
    tween?.kill()
    // 0 while hidden (display: none). v-show only touches display, so these inline sizes stay.
    const from = pane.getBoundingClientRect().width
    paneOpen.value = true
    gsap.set(pane, { width: from, marginLeft: from === 0 ? -GAP : 0, overflow: 'hidden' })
    gsap.set(inner, { width: Math.max(from, width) })
    tween = gsap.to(pane, {
      width,
      // The flex gap would leave 5 px when the pane is closed: a negative margin takes it back
      marginLeft: width === 0 ? -GAP : 0,
      duration: dur(width > from ? DURATION.tileOpen : DURATION.tileClose),
      ease: EASE.emphasized,
      onComplete: () => {
        tween = null
        gsap.set(pane, { clearProps: 'width,marginLeft,overflow' })
        gsap.set(inner, { clearProps: 'width' })
        done?.()
      },
    })
  }

  /** Phones: the list and the record take turns; the one arriving slides in from its side. */
  function slideIn (el: HTMLElement | null, from: number): void {
    if (el) {
      gsap.fromTo(el, { x: from, autoAlpha: 0 }, {
        x: 0, autoAlpha: 1, duration: dur(DURATION.page), clearProps: 'transform,opacity,visibility',
      })
    }
  }

  watch([paneShown, mdAndUp, restingWidth], async ([shown, desktop, width], [wasShown, wasDesktop, wasWidth]) => {
    if (!desktop || !wasDesktop) {
      // Phones, or crossing 768 px: no width to animate
      tween?.kill()
      paneOpen.value = shown
      if (paneEl.value) {
        gsap.set(paneEl.value, { clearProps: 'width,marginLeft,overflow' })
      }
      if (!desktop && wasDesktop === desktop && shown !== wasShown) {
        await nextTick()
        slideIn(shown ? paneEl.value : mainEl.value, shown ? -24 : 24)
      }
      return
    }
    if (shown !== wasShown || width !== wasWidth) {
      tweenPane(shown ? width : 0, shown
        ? undefined
        : () => {
          paneOpen.value = false
        })
    }
  })

  // The page's own header (PageBody) pins itself under the pane on phones: it needs the pane's height
  let paneObserver: ResizeObserver | null = null
  watch([stuck, paneEl], ([on, el]) => {
    paneObserver?.disconnect()
    paneObserver = null
    if (on && el && typeof ResizeObserver !== 'undefined') {
      paneObserver = new ResizeObserver(() => {
        rootEl.value?.style.setProperty('--pane-h', `${Math.floor(el.getBoundingClientRect().height)}px`)
      })
      paneObserver.observe(el)
    } else {
      rootEl.value?.style.removeProperty('--pane-h')
    }
  }, { flush: 'post', immediate: true })
  onBeforeUnmount(() => paneObserver?.disconnect())

  function toggle (): void {
    collapsed.value = !collapsed.value
    try {
      localStorage.setItem(COLLAPSED_KEY, collapsed.value ? '1' : '0')
    } catch {
      // A per-device convenience: without storage the pane opens again next time
    }
  }

  function readCollapsed (): boolean {
    try {
      return localStorage.getItem(COLLAPSED_KEY) === '1'
    } catch {
      return false
    }
  }

  provide(paneKey, { target, blocks, selected, pinned, collapsed, canExpand, toggle })
  provide(shellKey, 'app')

  watch(() => route.name, () => {
    if (isAdmin.value) {
      void registrations.refresh()
    }
  }, { immediate: true })
</script>
