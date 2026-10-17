<template>
  <AuthCard lead="Enter the email you log in with. We’ll send a link that works once, for 1 hour." title="Reset your password">
    <FeedbackBanner v-if="sent" :icon="mdiEmailOutline" type="info">
      If that email is registered, a link is on its way. Check your inbox and spam folder.
    </FeedbackBanner>

    <FeedbackBanner v-if="failure" type="error">{{ failure }}</FeedbackBanner>

    <form class="flex flex-col gap-4" novalidate @submit.prevent="submit">
      <FormField id="email" label="Email">
        <v-text-field
          id="email"
          v-model="email"
          autocomplete="username"
          :error-messages="invalid"
          inputmode="email"
          name="email"
          spellcheck="false"
          type="email"
        />
      </FormField>

      <v-btn block color="primary" :loading="busy" type="submit">{{ sent ? 'Send another link' : 'Send link' }}</v-btn>
    </form>

    <router-link class="flex min-h-12 items-center font-medium text-primary" :to="{ name: 'login' }">Back to log in</router-link>
  </AuthCard>
</template>

<script lang="ts" setup>
  import { mdiEmailOutline } from '@mdi/js'
  import { ref } from 'vue'
  import { authApi } from '@/api/auth'
  import { NetworkError } from '@/api/problem'
  import { focusFirstError } from '@/app/composables/focusFirstError'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import FormField from '@/components/FormField.vue'
  import AuthCard from './AuthCard.vue'

  // AFD J2 steps 2–3 (AUTH-8): the same answer whether or not the email is registered.
  const email = ref('')
  const sent = ref(false)
  const busy = ref(false)
  const invalid = ref<string>()
  const failure = ref<string | null>(null)

  async function submit (): Promise<void> {
    invalid.value = /^[^@\s]+@[^@\s]+\.[^@\s.]{2,}$/.test(email.value.trim()) ? undefined : 'Enter a valid email'
    failure.value = null
    if (invalid.value) {
      await focusFirstError()
      return
    }
    if (busy.value) {
      return
    }
    busy.value = true
    try {
      await authApi.requestReset(email.value.trim())
      sent.value = true
    } catch (error) {
      failure.value = error instanceof NetworkError
        ? 'No connection. Check your signal and try again.'
        : 'Something went wrong on our side. Try again in a minute.'
    } finally {
      busy.value = false
    }
  }
</script>
