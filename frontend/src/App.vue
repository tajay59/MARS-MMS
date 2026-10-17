<template>
  <v-app>
    <component :is="shell" v-if="session.ready">
      <router-view />
    </component>

    <UpdatePrompt />
  </v-app>
</template>

<script lang="ts" setup>
  import { computed } from 'vue'
  import { useRoute } from 'vue-router'
  import { useDisplay, useTheme } from 'vuetify'
  import { usePwa } from '@/app/pwa/usePwa'
  import AppShell from '@/app/shells/AppShell.vue'
  import FieldShell from '@/app/shells/FieldShell.vue'
  import PublicShell from '@/app/shells/PublicShell.vue'
  import UpdatePrompt from '@/components/UpdatePrompt.vue'
  import { useSessionStore } from '@/stores/session'
  import { useThemeStore } from '@/stores/theme'

  useThemeStore().init(useTheme())
  usePwa()

  const session = useSessionStore()
  const route = useRoute()
  const { mobile } = useDisplay()

  /*
    The shell around each page (AFD §5.1): the split panel for public pages, the app shell (rail,
    pane and view) for staff and clients, and the field shell for staff on phones on /scan, /sync
    and /visits/:id/field.
  */
  const shell = computed(() => {
    if (route.meta.layout === 'public' || !session.user) {
      return PublicShell
    }
    return route.meta.layout === 'field' && mobile.value && !session.isClient ? FieldShell : AppShell
  })
</script>
