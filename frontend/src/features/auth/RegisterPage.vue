<template>
  <AuthCard
    lead="For people at organizations whose stations we look after. We check each new account and email you when it’s approved."
    title="Create an account"
  >
    <FeedbackBanner v-if="failure" type="error">{{ failure }}</FeedbackBanner>

    <form class="flex flex-col gap-4" novalidate @submit.prevent="submit">
      <FormField id="name" label="Your name">
        <v-text-field
          id="name"
          v-model="form.name"
          autocomplete="name"
          :error-messages="errors.name"
          name="name"
        />
      </FormField>

      <FormField id="email" label="Email">
        <v-text-field
          id="email"
          v-model="form.email"
          autocomplete="email"
          :error-messages="errors.email"
          inputmode="email"
          name="email"
          spellcheck="false"
          type="email"
        />
      </FormField>

      <FormField id="phone" label="Phone (optional)">
        <v-text-field
          id="phone"
          v-model="form.phone"
          autocomplete="tel"
          :error-messages="errors.phone"
          name="phone"
          type="tel"
        />
      </FormField>

      <FormField id="org" label="Your organization">
        <v-text-field
          id="org"
          v-model="form.organization"
          autocomplete="organization"
          :error-messages="errors.organization_name"
          hint="We’ll link your account to it."
          name="organization"
          persistent-hint
        />
      </FormField>

      <PasswordField
        id="password"
        v-model="form.password"
        autocomplete="new-password"
        :error="passwordError(submitted)"
        :hint="passwordHint"
        :hint-ok="passwordOk"
        label="Password"
        name="password"
      />

      <v-btn
        block
        class="mt-2"
        color="primary"
        :loading="busy"
        type="submit"
      >Register</v-btn>
    </form>

    <p class="m-0 text-sm text-surface-900">
      Already have an account?
      <router-link class="font-medium text-primary underline underline-offset-2" :to="{ name: 'login' }">Log in</router-link>
    </p>
  </AuthCard>
</template>

<script lang="ts" setup>
  import { reactive, ref, toRef } from 'vue'
  import { useRouter } from 'vue-router'
  import { authApi } from '@/api/auth'
  import { ApiError, NetworkError } from '@/api/problem'
  import { focusFirstError } from '@/app/composables/focusFirstError'
  import { usePasswordRule } from '@/app/composables/usePasswordRule'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import FormField from '@/components/FormField.vue'
  import PasswordField from '@/components/PasswordField.vue'
  import AuthCard from './AuthCard.vue'

  // AFD J1 steps 1–2 (AUTH-1, AUTH-2). The answer is the same for a new or an existing email.
  const router = useRouter()
  const form = reactive({ name: '', email: '', phone: '', organization: '', password: '' })
  const errors = ref<Record<string, string>>({})
  const failure = ref<string | null>(null)
  const busy = ref(false)
  const submitted = ref(false)
  const passwordServerError = ref<string>()
  const { long: passwordOk, hint: passwordHint, error: passwordError } = usePasswordRule(toRef(form, 'password'), passwordServerError)

  function check (): boolean {
    const found: Record<string, string> = {}
    if (!form.name.trim()) {
      found.name = 'Enter your name'
    }
    if (!/^[^@\s]+@[^@\s]+\.[^@\s.]{2,}$/.test(form.email.trim())) {
      found.email = 'Enter a valid email'
    }
    if (!form.organization.trim()) {
      found.organization_name = 'Enter your organization’s name'
    }
    errors.value = found
    return Object.keys(found).length === 0 && passwordOk.value
  }

  async function submit (): Promise<void> {
    submitted.value = true
    passwordServerError.value = undefined
    failure.value = null
    if (busy.value) {
      return
    }
    if (!check()) {
      await focusFirstError()
      return
    }
    busy.value = true
    try {
      await authApi.register({
        name: form.name.trim(),
        email: form.email.trim(),
        phone: form.phone.trim() || null,
        organization_name: form.organization.trim(),
        password: form.password,
      })
      // The email travels in history state, not the URL, so it stays out of server logs.
      await router.push({ name: 'register-pending', state: { email: form.email.trim() } })
    } catch (error) {
      if (error instanceof ApiError && error.status === 422) {
        const fields = error.fieldErrors()
        passwordServerError.value = fields.password
        delete fields.password
        errors.value = fields
        if (Object.keys(fields).length === 0 && !passwordServerError.value) {
          failure.value = error.detail
        }
        await focusFirstError()
      } else if (error instanceof NetworkError) {
        failure.value = 'No connection. Check your signal and try again.'
      } else if (error instanceof ApiError && error.status === 429) {
        failure.value = 'Too many attempts. Wait a minute, then try again.'
      } else {
        failure.value = 'Something went wrong on our side. Try again in a minute.'
      }
    } finally {
      busy.value = false
    }
  }
</script>
