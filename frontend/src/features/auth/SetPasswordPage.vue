<template>
  <AuthCard :lead="lead" :title="mode === 'invite' ? `Welcome to ${APP_NAME}` : 'Set a new password'">
    <template v-if="expired">
      <FeedbackBanner type="warning">This link has expired. We can send you a new one.</FeedbackBanner>
      <v-btn block color="primary" :to="{ name: 'forgot-password' }">Send a new link</v-btn>
    </template>

    <form v-else class="flex flex-col gap-4" novalidate @submit.prevent="submit">
      <FeedbackBanner v-if="failure" type="error">{{ failure }}</FeedbackBanner>

      <PasswordField
        id="new-password"
        v-model="password"
        autocomplete="new-password"
        :error="passwordError(submitted)"
        :hint="passwordHint"
        :hint-ok="passwordOk"
        label="New password"
        name="new-password"
      />

      <PasswordField
        id="again"
        v-model="again"
        autocomplete="new-password"
        :error="mismatch ? 'The two passwords are different' : undefined"
        label="Type it again"
        name="again"
      />

      <p class="m-0 text-sm text-surface-600">
        {{ mode === 'invite' ? "You’ll go straight to your dashboard." : 'Saving logs you out on every other device.' }}
      </p>

      <v-btn block color="primary" :loading="busy" type="submit">Save</v-btn>
    </form>
  </AuthCard>
</template>

<script lang="ts" setup>
  import { computed, ref } from 'vue'
  import { useRouter } from 'vue-router'
  import { authApi } from '@/api/auth'
  import { ApiError, NetworkError } from '@/api/problem'
  import { APP_NAME } from '@/app/brand'
  import { focusFirstError } from '@/app/composables/focusFirstError'
  import { usePasswordRule } from '@/app/composables/usePasswordRule'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import PasswordField from '@/components/PasswordField.vue'
  import { useSessionStore } from '@/stores/session'
  import AuthCard from './AuthCard.vue'

  // /reset-password/:token (AFD J2 steps 4–5) and /invite/:token (J1, invited users).
  const props = defineProps<{ token: string, mode: 'reset' | 'invite' }>()

  const router = useRouter()
  const session = useSessionStore()
  const password = ref('')
  const again = ref('')
  const busy = ref(false)
  const submitted = ref(false)
  const expired = ref(false)
  const failure = ref<string | null>(null)
  const passwordServerError = ref<string>()
  const { long: passwordOk, hint: passwordHint, error: passwordError } = usePasswordRule(password, passwordServerError)
  const mismatch = computed(() => submitted.value && again.value !== password.value)

  const lead = computed(() => {
    if (expired.value) {
      return props.mode === 'invite' ? 'Invitation links work for 7 days and only once.' : 'Reset links work for 1 hour and only once.'
    }
    return props.mode === 'invite' ? 'Choose a password to finish setting up your account.' : 'Choose a password you don’t use anywhere else.'
  })

  async function submit (): Promise<void> {
    submitted.value = true
    passwordServerError.value = undefined
    failure.value = null
    if (busy.value) {
      return
    }
    if (!passwordOk.value || mismatch.value) {
      await focusFirstError()
      return
    }
    busy.value = true
    try {
      if (props.mode === 'invite') {
        await session.acceptInvitation(props.token, password.value)
        await router.replace({ name: 'dashboard' })
      } else {
        await authApi.confirmReset(props.token, password.value)
        await router.replace({ name: 'login', query: { notice: 'password-changed' } })
      }
    } catch (error) {
      if (error instanceof ApiError && (error.status === 410 || error.code === 'link_expired')) {
        expired.value = true
      } else if (error instanceof ApiError && error.status === 429) {
        // The gateway limits these requests (10 a minute): say so, and it is safe to send again
        failure.value = 'Too many attempts. Wait a minute, then try again.'
      } else if (error instanceof ApiError && error.status === 422) {
        passwordServerError.value = error.fieldErrors().password ?? error.detail
        await focusFirstError()
      } else if (error instanceof ApiError && error.code === 'account_blocked') {
        failure.value = 'This account cannot sign in. Contact the service desk.'
      } else if (error instanceof NetworkError) {
        failure.value = 'No connection. Check your signal and try again.'
      } else {
        failure.value = 'Something went wrong on our side. Try again in a minute.'
      }
    } finally {
      busy.value = false
    }
  }
</script>
