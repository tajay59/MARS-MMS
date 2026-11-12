<template>
  <AuthCard
    :lead="codes ? undefined : 'Your role needs it to log in. It takes about a minute.'"
    :title="codes ? 'Save your recovery codes' : 'Set up two-step sign-in'"
  >
    <template v-if="codes">
      <p class="m-0 text-sm text-surface-900">If you lose your phone, each of these codes lets you log in once. Keep them somewhere safe, such as a password manager.</p>
      <RecoveryCodes :codes="codes" done-label="Continue" :email="email" @done="finish" />
    </template>

    <template v-else>
      <FeedbackBanner type="warning">Your time to set this up has ended. Set it up now to log in.</FeedbackBanner>

      <FeedbackBanner v-if="failure" :type="failure.type">{{ failure.text }}</FeedbackBanner>

      <div v-if="loading" aria-label="Getting your key…" class="flex flex-col gap-2" role="status">
        <v-skeleton-loader type="image, text" />
      </div>

      <form v-else-if="setup" class="flex flex-col gap-6" novalidate @submit.prevent="submit">
        <section aria-labelledby="enrol-1" class="flex flex-col gap-3">
          <h2 id="enrol-1" class="m-0 text-h3 text-surface-900">1. Scan this code with your authenticator app</h2>
          <TwoStepQr :email="email" :secret="setup.secret" :uri="setup.otpauth_uri" />
        </section>

        <section aria-labelledby="enrol-2" class="flex flex-col gap-3">
          <h2 id="enrol-2" class="m-0 text-h3 text-surface-900">2. Enter the 6-digit code it shows</h2>
          <OtpField id="enrol-code" v-model="code" :error="failure?.type === 'error'" label="6-digit code" />
        </section>

        <v-btn
          block
          color="primary"
          :loading="busy"
          type="submit"
        >Continue</v-btn>
      </form>
    </template>
  </AuthCard>
</template>

<script lang="ts" setup>
  import type { Me, TotpSetupOut } from '@/api/models'
  import { onMounted, ref } from 'vue'
  import { authApi } from '@/api/auth'
  import { ApiError, NetworkError } from '@/api/problem'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import { useSessionStore } from '@/stores/session'
  import AuthCard from '../AuthCard.vue'
  import OtpField from './OtpField.vue'
  import RecoveryCodes from './RecoveryCodes.vue'
  import TwoStepQr from './TwoStepQr.vue'

  // Logging in after the setup window has ended (W22-6): the password was right, but the role
  // needs two-step sign-in and the person has none. The challenge only allows these two calls.
  // The session starts when the code is confirmed; the recovery codes come before the dashboard.
  const props = defineProps<{ challenge: string, email: string }>()
  const emit = defineEmits<{
    done: [user: Me]
    restart: [notice?: { type: 'info' | 'warning' | 'error', text: string }]
  }>()

  type Banner = { type: 'info' | 'warning' | 'error', text: string }
  const session = useSessionStore()
  const setup = ref<TotpSetupOut | null>(null)
  const loading = ref(true)
  const code = ref('')
  const busy = ref(false)
  const failure = ref<Banner | null>(null)
  const codes = ref<string[] | null>(null)
  const user = ref<Me | null>(null)

  onMounted(async () => {
    try {
      setup.value = await authApi.enrolBegin(props.challenge)
    } catch (error) {
      if (error instanceof ApiError && error.reason === 'invalid_challenge') {
        emit('restart', { type: 'info', text: 'That took too long. Log in again to set up two-step sign-in.' })
      } else {
        failure.value = error instanceof NetworkError
          ? { type: 'error', text: 'No connection. Check your signal and try again.' }
          : { type: 'error', text: 'Something went wrong on our side. Try again in a minute.' }
      }
    } finally {
      loading.value = false
    }
  })

  function finish (): void {
    if (user.value) {
      emit('done', user.value)
    }
  }

  async function submit (): Promise<void> {
    if (busy.value) {
      return
    }
    if (code.value.length < 6) {
      failure.value = { type: 'error', text: 'Enter the 6-digit code.' }
      return
    }
    busy.value = true
    failure.value = null
    try {
      const answer = await authApi.enrolConfirm(props.challenge, code.value)
      user.value = session.finishLogin(answer)
      codes.value = answer.recovery_codes ?? []
    } catch (error) {
      code.value = ''
      if (error instanceof NetworkError) {
        failure.value = { type: 'error', text: 'No connection. Check your signal and try again.' }
      } else if (error instanceof ApiError && error.status === 429) {
        failure.value = { type: 'warning', text: 'Too many attempts. Try again in 15 minutes.' }
      } else if (error instanceof ApiError && error.reason === 'invalid_challenge') {
        emit('restart', { type: 'info', text: 'That took too long. Log in again to set up two-step sign-in.' })
      } else if (error instanceof ApiError && error.reason === 'invalid_code') {
        failure.value = { type: 'error', text: 'That code is incorrect. Enter the current code from your app.' }
      } else {
        failure.value = { type: 'error', text: 'Something went wrong on our side. Try again in a minute.' }
      }
    } finally {
      busy.value = false
    }
  }
</script>
