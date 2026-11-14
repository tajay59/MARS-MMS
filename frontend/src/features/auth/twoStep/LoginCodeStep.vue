<template>
  <AuthCard
    :lead="useRecovery
      ? 'Enter one of the codes you saved when you set up two-step sign-in. Each code works once.'
      : 'Open your authenticator app and enter the 6-digit code for MARS-MMS.'"
    :title="useRecovery ? 'Use a recovery code' : 'Enter your code'"
  >
    <FeedbackBanner v-if="failure" :type="failure.type">{{ failure.text }}</FeedbackBanner>

    <form class="flex flex-col gap-4" novalidate @submit.prevent="submit">
      <p class="m-0 flex flex-wrap items-baseline justify-between gap-x-3 text-sm text-surface-600">
        <span>Logging in as <span class="font-mono text-surface-900">{{ email }}</span></span>
        <button class="text-sm font-medium text-primary" type="button" @click="emit('restart')">Use a different account</button>
      </p>

      <FormField v-if="useRecovery" id="recovery" label="Recovery code">
        <v-text-field
          id="recovery"
          ref="recoveryField"
          v-model="recovery"
          autocapitalize="characters"
          autocomplete="off"
          class="font-mono"
          :error="failure?.type === 'error'"
          hide-details
          name="recovery-code"
          spellcheck="false"
        />

        <p class="m-0 text-sm text-surface-600">10 letters and numbers, with or without the dash.</p>
      </FormField>

      <OtpField
        v-else
        id="code"
        v-model="code"
        autofocus
        :disabled="locked"
        :error="failure?.type === 'error'"
        hint="The code changes every 30 seconds."
        label="6-digit code"
      />

      <v-btn
        block
        class="mt-2"
        color="primary"
        :disabled="locked"
        :loading="busy"
        type="submit"
      >Log in</v-btn>
    </form>

    <div class="flex flex-col gap-4 border-t border-surface-200 pt-6">
      <p v-if="!useRecovery" class="m-0 text-sm text-surface-600">Lost your phone? Each recovery code you saved when you set this up works once.</p>

      <v-btn block class="text-primary" variant="outlined" @click="swap">{{ useRecovery ? 'Back to the 6-digit code' : 'Use a recovery code' }}</v-btn>
    </div>
  </AuthCard>
</template>

<script lang="ts" setup>
  import type { Me } from '@/api/models'
  import { nextTick, ref } from 'vue'
  import { authApi, type TotpFactor } from '@/api/auth'
  import { ApiError, NetworkError } from '@/api/problem'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import FormField from '@/components/FormField.vue'
  import { useSessionStore } from '@/stores/session'
  import AuthCard from '../AuthCard.vue'
  import OtpField from './OtpField.vue'

  // The second step of logging in (W22; TRD §6.1.1; AFD J2): a code from the authenticator app,
  // or a recovery code. The challenge from the password step is the only thing carried here; it is
  // kept in memory, used once and good for five minutes. Wrong answers never say more than that
  // the code is incorrect.
  const props = defineProps<{ challenge: string, email: string }>()
  const emit = defineEmits<{
    done: [user: Me]
    /** Back to the password step, with a message when the challenge ran out. */
    restart: [notice?: { type: 'info' | 'warning' | 'error', text: string }]
  }>()

  type Banner = { type: 'info' | 'warning' | 'error', text: string }
  const session = useSessionStore()
  const code = ref('')
  const recovery = ref('')
  const useRecovery = ref(false)
  const busy = ref(false)
  const locked = ref(false)
  const failure = ref<Banner | null>(null)
  const recoveryField = ref<{ focus: () => void } | null>(null)

  async function swap (): Promise<void> {
    useRecovery.value = !useRecovery.value
    failure.value = null
    code.value = ''
    recovery.value = ''
    await nextTick()
    recoveryField.value?.focus()
  }

  async function submit (): Promise<void> {
    if (busy.value || locked.value) {
      return
    }
    const factor: TotpFactor = useRecovery.value ? { recovery_code: recovery.value.trim() } : { code: code.value }
    const missing = useRecovery.value ? recovery.value.trim().length === 0 : code.value.length < 6
    if (missing) {
      failure.value = { type: 'error', text: useRecovery.value ? 'Enter a recovery code.' : 'Enter the 6-digit code.' }
      return
    }
    busy.value = true
    failure.value = null
    try {
      const answer = await authApi.loginTotp(props.challenge, factor)
      const user = session.finishLogin(answer)
      if (useRecovery.value) {
        session.noteRecoveryUsed(user.recovery_codes_left)
      }
      emit('done', user)
    } catch (error) {
      if (!isGatewayLimit(error)) {
        code.value = ''
        recovery.value = ''
      }
      explain(error)
    } finally {
      busy.value = false
    }
  }

  /** A 429 from the gateway has no `retry_after`; the account lock (auth) always has one. */
  function isGatewayLimit (error: unknown): boolean {
    return error instanceof ApiError && error.status === 429 && error.retryAfter === undefined
  }

  function explain (error: unknown): void {
    if (error instanceof NetworkError) {
      failure.value = { type: 'error', text: 'No connection. Check your signal and try again.' }
    } else if (isGatewayLimit(error)) {
      // The address is over Nginx's limit for sign-in requests: nothing is locked, and what was
      // typed is kept, so waiting a minute and pressing Log in again is enough
      failure.value = { type: 'warning', text: 'Too many attempts. Wait a minute, then try again.' }
    } else if (error instanceof ApiError && error.status === 429) {
      locked.value = true
      failure.value = { type: 'warning', text: 'Too many attempts. Try again in 15 minutes.' }
    } else if (error instanceof ApiError && error.reason === 'invalid_challenge') {
      emit('restart', { type: 'info', text: 'That took too long. Log in again to get a new code step.' })
    } else if (error instanceof ApiError && error.reason === 'invalid_code') {
      failure.value = {
        type: 'error',
        text: useRecovery.value
          ? 'That recovery code is incorrect or already used.'
          : 'That code is incorrect. Enter the current code from your app.',
      }
    } else if (error instanceof ApiError && error.code === 'account_blocked') {
      failure.value = { type: 'error', text: 'This account cannot sign in. Contact the service desk.' }
    } else {
      failure.value = { type: 'error', text: 'Something went wrong on our side. Try again in a minute.' }
    }
  }
</script>
