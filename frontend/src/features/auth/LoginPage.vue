<template>
  <AuthCard title="Log in">
    <FeedbackBanner v-if="banner" :type="banner.type">{{ banner.text }}</FeedbackBanner>

    <form class="flex flex-col gap-4" novalidate @submit.prevent="submit">
      <FormField id="email" label="Email">
        <v-text-field
          id="email"
          v-model="email"
          autocomplete="username"
          hide-details
          inputmode="email"
          name="email"
          spellcheck="false"
          type="email"
        />
      </FormField>

      <PasswordField
        id="password"
        v-model="password"
        autocomplete="current-password"
        label="Password"
        name="password"
      >
        <template #aside>
          <router-link class="text-sm font-medium text-primary" :to="{ name: 'forgot-password' }">Forgot password?</router-link>
        </template>
      </PasswordField>

      <v-btn
        block
        class="mt-2"
        color="primary"
        :loading="busy"
        type="submit"
      >Log in</v-btn>
    </form>

    <div class="flex flex-col gap-4 border-t border-surface-200 pt-6">
      <p class="m-0 text-sm text-surface-600">
        New to {{ APP_NAME }}? Our team checks each new account before you can log in.
      </p>

      <v-btn block class="text-primary" :to="{ name: 'register' }" variant="outlined">Create an account</v-btn>
    </div>
  </AuthCard>
</template>

<script lang="ts" setup>
  import { computed, ref } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { ApiError, NetworkError } from '@/api/problem'
  import { APP_NAME } from '@/app/brand'
  import { safeNext } from '@/app/router/next'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import FormField from '@/components/FormField.vue'
  import PasswordField from '@/components/PasswordField.vue'
  import { useSessionStore } from '@/stores/session'
  import AuthCard from './AuthCard.vue'

  type Banner = { type: 'success' | 'info' | 'warning' | 'error', text: string }

  // AFD J2 and §6; TRD §6.1.1. Never says whether the email or the password was wrong.
  const route = useRoute()
  const router = useRouter()
  const session = useSessionStore()

  const email = ref('')
  const password = ref('')
  const busy = ref(false)
  const failure = ref<Banner | null>(null)

  // Why the user is here: a notice from the previous page or why the session ended.
  const arrival = computed<Banner | null>(() => {
    if (route.query.notice === 'password-changed') {
      return { type: 'success', text: 'Password changed. Log in with your new password.' }
    }
    switch (route.query.reason) {
      case 'session_expired':
      case 'session_revoked': {
        return { type: 'info', text: 'Your session ended. Log in to carry on where you were.' }
      }
      case 'account_blocked': {
        return { type: 'error', text: 'This account cannot sign in. Contact the service desk.' }
      }
      default: {
        return null
      }
    }
  })
  const banner = computed(() => failure.value ?? arrival.value)

  async function submit (): Promise<void> {
    if (busy.value) {
      return
    }
    if (!email.value.trim() || !password.value) {
      failure.value = { type: 'error', text: 'Enter your email and password.' }
      return
    }
    busy.value = true
    failure.value = null
    try {
      await session.login(email.value.trim(), password.value)
      await router.replace(safeNext(route.query.next) ?? { name: 'dashboard' })
    } catch (error) {
      password.value = ''
      failure.value = explain(error)
      if (error instanceof ApiError && error.code === 'account_pending') {
        await router.push({ name: 'register-pending', state: { email: email.value.trim() } })
      }
    } finally {
      busy.value = false
    }
  }

  function explain (error: unknown): Banner {
    if (error instanceof NetworkError) {
      return { type: 'error', text: 'No connection. Check your signal and try again.' }
    }
    if (error instanceof ApiError) {
      if (error.status === 429) {
        return { type: 'warning', text: 'Too many attempts. Try again in 15 minutes.' }
      }
      if (error.code === 'account_blocked') {
        return { type: 'error', text: 'This account cannot sign in. Contact the service desk.' }
      }
      if (error.status === 401) {
        return { type: 'error', text: 'Email or password is incorrect.' }
      }
    }
    return { type: 'error', text: 'Something went wrong on our side. Try again in a minute.' }
  }
</script>
