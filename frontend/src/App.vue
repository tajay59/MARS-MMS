<template>
  <v-app>
    <v-main>
      <router-view />
    </v-main>
  </v-app>
</template>

<script lang="ts" setup>
  import { useTheme } from 'vuetify'
  import { useThemeStore } from '@/stores/theme'

  useThemeStore().init(useTheme())
</script>
