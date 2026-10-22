<template>
  <!-- The rail: a slim tile of section icons that never expands (DBD "The app shell") -->
  <nav ref="nav" aria-label="Main" class="relative z-[3] flex w-16 shrink-0 flex-col items-center gap-1 bg-surface py-3">
    <!-- The active section's fill: one tile that slides to the section chosen (W4-10) -->
    <span
      ref="indicator"
      aria-hidden="true"
      class="invisible absolute left-2.5 top-0 size-11 rounded-xl bg-primary-100 opacity-0 dark:bg-primary-800"
    />

    <router-link
      :aria-label="`${APP_NAME} dashboard`"
      class="mb-3 flex size-11 shrink-0 items-center justify-center rounded-xl"
      :to="{ name: 'dashboard' }"
    >
      <AppLogo :size="32" :wordmark="false" />
    </router-link>

    <RailButton
      v-for="section in sections"
      :key="section.key"
      :active="section.key === current?.key"
      :badge="badges[section.key]"
      :hint="section.hint"
      :icon="section.icon"
      :label="section.label"
      :to="{ name: section.items[0]!.to }"
    />

    <div class="grow" />

    <RailButton
      v-if="!isClient"
      :active="route.name === 'sync'"
      :badge="uploadsLabel"
      :hint="uploadsLabel ? 'Photos and video are going up from this device' : 'Nothing is waiting on this device'"
      :icon="uploadsLabel ? mdiCloudUploadOutline : mdiCloudCheckOutline"
      label="Sync"
      :to="{ name: 'sync' }"
    />

    <RailButton
      :active="route.name === 'notifications'"
      :count="badgeText(notifications.unread)"
      hint="Updates on requests, visits and reports"
      :icon="icons.notifications"
      label="Notifications"
      :to="{ name: 'notifications' }"
    />

    <div class="mt-1 flex size-11 shrink-0 items-center justify-center">
      <UserMenu rail />
    </div>
  </nav>
</template>

<script lang="ts" setup>
  import type { Section } from '@/app/navigation'
  import { mdiCloudCheckOutline, mdiCloudUploadOutline } from '@mdi/js'
  import { storeToRefs } from 'pinia'
  import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
  import { useRoute } from 'vue-router'
  import { APP_NAME } from '@/app/brand'
  import { dur, DURATION, EASE, gsap } from '@/app/motion'
  import { icons } from '@/app/theme/icons'
  import AppLogo from '@/components/AppLogo.vue'
  import UserMenu from '@/components/UserMenu.vue'
  import { badgeText } from '@/features/notifications/notifications'
  import { uploadsLabel } from '@/features/visits/uploadQueues'
  import { useNotificationsStore } from '@/stores/notifications'
  import { useSessionStore } from '@/stores/session'
  import RailButton from './RailButton.vue'

  defineProps<{
    sections: Section[]
    current?: Section
    /** Per section key, what waits there ("2 waiting"); shown as a dot. */
    badges: Record<string, string | null>
  }>()

  const route = useRoute()
  const { isClient } = storeToRefs(useSessionStore())
  const notifications = useNotificationsStore()

  const nav = ref<HTMLElement | null>(null)
  const indicator = ref<HTMLElement | null>(null)
  let placed = false

  /** Moves the indicator to the active button; the first placement and resizes are instant. */
  function place (animate: boolean): void {
    const target = nav.value?.querySelector<HTMLElement>('[data-rail-button][data-active="true"]')
    if (!indicator.value) {
      return
    }
    if (!target) {
      gsap.to(indicator.value, { autoAlpha: 0, scale: 0.8, duration: dur(DURATION.hover) })
      placed = false
      return
    }
    const y = target.offsetTop
    if (!animate || !placed) {
      gsap.set(indicator.value, { y })
      gsap.to(indicator.value, { autoAlpha: 1, scale: 1, duration: animate ? dur(DURATION.hover) : 0 })
    } else {
      gsap.to(indicator.value, { y, autoAlpha: 1, scale: 1, duration: dur(0.35), ease: EASE.emphasized })
    }
    placed = true
  }

  // The bottom group moves with the window's height
  const resize = new ResizeObserver(() => place(false))

  onMounted(() => {
    place(false)
    if (nav.value) {
      resize.observe(nav.value)
    }
  })

  onBeforeUnmount(() => {
    resize.disconnect()
    gsap.killTweensOf(indicator.value)
  })

  watch(() => route.name, async () => {
    await nextTick()
    place(true)
  })
</script>
