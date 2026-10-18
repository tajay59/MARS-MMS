<template>
  <v-app>
    <component :is="shell" v-if="session.ready">
      <!--
        Page transitions (W4-10): the new page rises in; the old one goes at once, so the pane's
        blocks swap in one step and the pane doesn't close and reopen between two pages.
        A wrapper element because pages render several roots (PageBody's header and body).
      -->
      <router-view v-slot="{ Component, route: shown }">
        <Transition :css="false" @enter="pageEnter" @leave="pageLeave">
          <div :key="String(shown.name)" class="flex min-h-0 grow flex-col">
            <component :is="Component" />
          </div>
        </Transition>
      </router-view>
    </component>

    <UpdatePrompt />
  </v-app>
</template>

<script lang="ts" setup>
  import { computed } from 'vue'
  import { useRoute } from 'vue-router'
  import { useDisplay, useTheme } from 'vuetify'
  import { dur, DURATION, gsap } from '@/app/motion'
  import { usePwa } from '@/app/pwa/usePwa'
  import AppShell from '@/app/shells/AppShell.vue'
  import FieldShell from '@/app/shells/FieldShell.vue'
  import PublicShell from '@/app/shells/PublicShell.vue'
  import UpdatePrompt from '@/components/UpdatePrompt.vue'
  import { useBrandingStore } from '@/stores/branding'
  import { useSessionStore } from '@/stores/session'
  import { useThemeStore } from '@/stores/theme'

  const vuetifyTheme = useTheme()
  useThemeStore().init(vuetifyTheme)
  useBrandingStore().init(vuetifyTheme)
  usePwa()

  const session = useSessionStore()
  const route = useRoute()
  const { mobile } = useDisplay()

  /*
    The shell around each page (AFD §5.1): the split panel for public pages, the app shell (rail,
    pane and view) for staff and clients, and the field shell for staff on phones on /scan, /sync
    and /visits/:id/field.
  */
  function pageEnter (el: Element, done: () => void): void {
    gsap.fromTo(el, { autoAlpha: 0, y: 8 }, {
      autoAlpha: 1,
      y: 0,
      duration: dur(DURATION.page),
      clearProps: 'transform,opacity,visibility',
      onComplete: done,
    })
  }

  function pageLeave (_el: Element, done: () => void): void {
    done()
  }

  const shell = computed(() => {
    if (route.meta.layout === 'public' || !session.user) {
      return PublicShell
    }
    return route.meta.layout === 'field' && mobile.value && !session.isClient ? FieldShell : AppShell
  })
</script>
