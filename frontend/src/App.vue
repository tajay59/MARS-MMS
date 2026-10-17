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
  import ClientShell from '@/app/shells/ClientShell.vue'
  import FieldShell from '@/app/shells/FieldShell.vue'
  import PublicShell from '@/app/shells/PublicShell.vue'
  import StaffShell from '@/app/shells/StaffShell.vue'
  import UpdatePrompt from '@/components/UpdatePrompt.vue'
  import { useSessionStore } from '@/stores/session'
  import { useThemeStore } from '@/stores/theme'

  useThemeStore().init(useTheme())
  usePwa()

  const session = useSessionStore()
  const route = useRoute()
  const { mobile } = useDisplay()

  /*
    The shell around each page (AFD §5.1): the split panel for public pages, the client or staff
    shell by role, and the field shell for staff on phones on /scan, /sync and /visits/:id/field.
  */
  const shell = computed(() => {
    if (route.meta.layout === 'public' || !session.user) {
      return PublicShell
    }
    if (session.isClient) {
      return ClientShell
    }
    return route.meta.layout === 'field' && mobile.value ? FieldShell : StaffShell
  })
</script>
