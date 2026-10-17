<template>
  <v-main class="bg-background">
    <div class="flex min-h-dvh flex-col md:flex-row">
      <!-- Split panel (DBD "The three shells"): primary-950 with the logo; no station photo yet (D5) -->
      <aside
        class="flex h-[120px] shrink-0 items-end bg-primary-950 px-4 pb-6 text-white md:h-auto md:w-2/5 md:flex-col md:items-stretch md:justify-between md:p-12 dark:bg-primary-900"
      >
        <AppLogo :size="mdAndUp ? 48 : 36" surface="dark" />

        <div aria-hidden="true" class="hidden grow items-center justify-center md:flex">
          <img
            alt=""
            class="h-auto w-full max-w-72 opacity-95"
            height="288"
            :src="logo.mark"
            width="288"
          >
        </div>

        <p class="m-0 hidden max-w-[40ch] text-sm text-primary-200 md:block">{{ APP_LONG_NAME }}</p>
      </aside>

      <main class="flex grow justify-center px-4 py-8 md:items-center md:px-6 md:py-12">
        <v-defaults-provider :defaults="mdAndUp ? {} : phoneDefaults">
          <div class="w-full max-w-[440px]">
            <slot />
          </div>
        </v-defaults-provider>
      </main>
    </div>
  </v-main>
</template>

<script lang="ts" setup>
  import { useDisplay } from 'vuetify'
  import { APP_LONG_NAME, logo } from '@/app/brand'
  import AppLogo from '@/components/AppLogo.vue'

  const { mdAndUp } = useDisplay()

  // Phones: 48 px fields and buttons, as in the field shell (TRD §13.2).
  const phoneDefaults = {
    VBtn: { height: 48 },
    VTextField: { density: 'comfortable' },
  }
</script>
