<template>
  <v-card class="flex flex-col items-center gap-4 border border-surface-200 px-4 py-8 text-center md:p-8">
    <div class="flex size-20 items-center justify-center rounded-full bg-warning-container">
      <v-icon class="text-warning" :icon="mdiClockOutline" size="48" />
    </div>

    <h1 class="m-0 text-2xl font-semibold leading-8 text-surface-900">Waiting for approval</h1>
    <p class="m-0 text-body text-surface-900">We’ll email you when your account is approved.</p>

    <p class="m-0 text-sm text-surface-600">
      <template v-if="email">We’ll write to <strong class="font-semibold text-surface-900">{{ email }}</strong>. </template>
      Check your spam folder if nothing arrives.
    </p>

    <router-link class="mt-2 flex min-h-12 items-center font-medium text-primary" :to="{ name: 'login' }">Back to log in</router-link>
  </v-card>
</template>

<script lang="ts" setup>
  import { mdiClockOutline } from '@mdi/js'

  // AFD J1 step 2, and a login attempt by a pending account (AFD §6).
  const state: unknown = window.history.state
  const email = typeof (state as { email?: unknown } | null)?.email === 'string' ? (state as { email: string }).email : null
</script>
