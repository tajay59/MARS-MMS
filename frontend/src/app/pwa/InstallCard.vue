<template>
  <section v-if="show" aria-labelledby="install-card-h" class="flex max-w-2xl flex-col gap-3 rounded-card bg-primary-50 p-4 text-primary-900 dark:bg-primary-900 dark:text-primary-50">
    <div class="flex items-center gap-3">
      <AppLogo class="shrink-0" :size="40" />

      <div>
        <h2 id="install-card-h" class="m-0 text-lg font-semibold">Install {{ APP_NAME }}</h2>
        <p class="m-0 text-sm">Opens from your home screen and works with no signal.</p>
      </div>
    </div>

    <p class="m-0 text-sm">Installing also lets the phone keep your saved visits safe. You need it for field work.</p>

    <div class="flex gap-3">
      <v-btn class="grow" variant="outlined" @click="hideInstallOffer()">Not now</v-btn>
      <v-btn class="grow" color="primary" @click="promptInstall()">Install</v-btn>
    </div>
  </section>
</template>

<script lang="ts" setup>
  import { computed } from 'vue'
  import { APP_NAME } from '@/app/brand'
  import AppLogo from '@/components/AppLogo.vue'
  import { useSessionStore } from '@/stores/session'
  import { hideInstallOffer, offerInstall, promptInstall } from './install'

  // Shown once on the dashboard to technicians and admins, where the browser offers installing
  // (Android Chrome, desktop Chrome and Edge). The Install row on My profile stays after "Not now".
  const session = useSessionStore()
  const show = computed(() => offerInstall.value && session.isStaff && session.canAct)
</script>
