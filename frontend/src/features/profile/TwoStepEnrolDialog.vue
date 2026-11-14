<template>
  <ModalSheet v-model="open" labelledby="ts-enrol-h" :max-width="480" persistent>
    <div class="flex flex-col gap-4">
      <div aria-hidden="true" class="flex gap-1.5">
        <span v-for="n in 3" :key="n" class="h-1 grow rounded-full" :class="n <= position ? 'bg-primary' : 'bg-surface-300'" />
      </div>

      <!-- 1 · Confirm it's you -->
      <form v-if="step === 'password'" class="flex flex-col gap-4" novalidate @submit.prevent="begin">
        <div class="flex flex-col gap-2">
          <h2 id="ts-enrol-h" class="m-0 text-h2 text-surface-900">Set up two-step sign-in</h2>
          <p class="m-0 text-sm text-surface-900">Every time you log in, you’ll enter a 6-digit code from an app on your phone as well as your password. Enter your password to start.</p>
        </div>

        <FeedbackBanner v-if="problem" type="error">{{ problem }}</FeedbackBanner>

        <PasswordField
          id="ts-password"
          v-model="password"
          autocomplete="current-password"
          :error="passwordError"
          label="Password"
        />

        <div class="flex justify-end gap-2">
          <v-btn class="text-primary" variant="text" @click="close">Cancel</v-btn>
          <v-btn color="primary" :loading="busy" type="submit">Continue</v-btn>
        </div>
      </form>

      <!-- 2 · Add the account -->
      <div v-else-if="step === 'scan' && setup" class="flex flex-col gap-4">
        <div class="flex flex-col gap-2">
          <h2 id="ts-enrol-h" class="m-0 text-h2 text-surface-900">Scan the QR code</h2>
          <p class="m-0 text-sm text-surface-900">Open your authenticator app, add an account and scan this code.</p>
        </div>

        <TwoStepQr :email="email" :secret="setup.secret" :uri="setup.otpauth_uri" />

        <div class="flex justify-end gap-2">
          <v-btn class="text-primary" variant="text" @click="step = 'password'">Back</v-btn>
          <v-btn color="primary" @click="step = 'code'">Continue</v-btn>
        </div>
      </div>

      <!-- 3 · Prove it works -->
      <form v-else-if="step === 'code'" class="flex flex-col gap-4" novalidate @submit.prevent="confirm">
        <div class="flex flex-col gap-2">
          <h2 id="ts-enrol-h" class="m-0 text-h2 text-surface-900">Enter the code from your app</h2>
          <p class="m-0 text-sm text-surface-900">Type the 6-digit code now showing for MARS-MMS. This checks that the app and this server agree.</p>
        </div>

        <FeedbackBanner v-if="problem" :type="problemType">{{ problem }}</FeedbackBanner>

        <OtpField
          id="ts-code"
          v-model="code"
          autofocus
          :error="problemType === 'error' && Boolean(problem)"
          label="6-digit code"
        />

        <div class="flex justify-end gap-2">
          <v-btn class="text-primary" variant="text" @click="step = 'scan'">Back</v-btn>
          <v-btn color="primary" :loading="busy" type="submit">Turn on</v-btn>
        </div>

        <p class="m-0 text-xs text-surface-600">Next: your recovery codes. Your other devices stay logged in.</p>
      </form>

      <!-- Recovery codes, shown once -->
      <div v-else-if="step === 'codes'" class="flex flex-col gap-4">
        <div class="flex flex-col gap-2">
          <h2 id="ts-enrol-h" class="m-0 text-h2 text-surface-900">Save your recovery codes</h2>
          <p class="m-0 text-sm text-surface-900">If you lose your phone, each of these codes lets you log in once. Keep them somewhere safe, such as a password manager.</p>
        </div>

        <RecoveryCodes :codes="codes" :email="email" @done="finish" />
      </div>
    </div>
  </ModalSheet>
</template>

<script lang="ts" setup>
  import type { TotpSetupOut } from '@/api/models'
  import { computed, ref, watch } from 'vue'
  import { totpApi } from '@/api/auth'
  import { ApiError, NetworkError } from '@/api/problem'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import ModalSheet from '@/components/ModalSheet.vue'
  import PasswordField from '@/components/PasswordField.vue'
  import OtpField from '@/features/auth/twoStep/OtpField.vue'
  import RecoveryCodes from '@/features/auth/twoStep/RecoveryCodes.vue'
  import TwoStepQr from '@/features/auth/twoStep/TwoStepQr.vue'
  import { useSessionStore } from '@/stores/session'

  // Turning on two-step sign-in from My profile (W22-7): the password, the QR code, a code that
  // proves the app has it, then the recovery codes. Nothing is on until the code is confirmed.
  // Persistent: a click outside must not lose the recovery codes before they are saved.
  const open = defineModel<boolean>({ required: true })
  const emit = defineEmits<{ changed: [] }>()

  type Step = 'password' | 'scan' | 'code' | 'codes'
  const session = useSessionStore()
  const email = computed(() => session.user?.email ?? '')
  const step = ref<Step>('password')
  const position = computed(() => step.value === 'password' ? 1 : (step.value === 'scan' ? 2 : 3))
  const password = ref('')
  const code = ref('')
  const setup = ref<TotpSetupOut | null>(null)
  const codes = ref<string[]>([])
  const busy = ref(false)
  const problem = ref<string | null>(null)
  const problemType = ref<'error' | 'warning'>('error')
  const passwordError = ref<string | undefined>()

  watch(open, isOpen => {
    if (isOpen) {
      step.value = 'password'
      password.value = ''
      code.value = ''
      setup.value = null
      codes.value = []
      problem.value = null
      passwordError.value = undefined
    }
  })

  function close (): void {
    open.value = false
  }

  function say (error: unknown, kind: 'error' | 'warning' = 'error'): void {
    problemType.value = kind
    if (error instanceof NetworkError) {
      problem.value = 'This needs a connection. Try again when you have signal.'
    } else if (error instanceof ApiError && error.status === 429) {
      problemType.value = 'warning'
      problem.value = 'Too many attempts. Try again in 15 minutes.'
    } else {
      problem.value = 'Something went wrong on our side. Try again in a minute.'
    }
  }

  async function begin (): Promise<void> {
    if (busy.value) {
      return
    }
    problem.value = null
    passwordError.value = undefined
    if (!password.value) {
      passwordError.value = 'Enter your password.'
      return
    }
    busy.value = true
    try {
      setup.value = await totpApi.begin(password.value)
      password.value = ''
      step.value = 'scan'
    } catch (error) {
      if (error instanceof ApiError && error.fieldCode('password') === 'wrong_password') {
        passwordError.value = 'Password is incorrect.'
      } else if (error instanceof ApiError && error.code === 'totp_enabled') {
        await session.reloadMe()
        emit('changed')
        close()
      } else {
        say(error)
      }
    } finally {
      busy.value = false
    }
  }

  async function confirm (): Promise<void> {
    if (busy.value) {
      return
    }
    problem.value = null
    if (code.value.length < 6) {
      problemType.value = 'error'
      problem.value = 'Enter the 6-digit code.'
      return
    }
    busy.value = true
    try {
      codes.value = (await totpApi.confirm(code.value)).recovery_codes
      await session.reloadMe()
      step.value = 'codes'
    } catch (error) {
      code.value = ''
      if (error instanceof ApiError && error.fieldCode('code') === 'wrong_code') {
        problemType.value = 'error'
        problem.value = 'That code is incorrect. Enter the current code from your app.'
      } else if (error instanceof ApiError && error.fieldCode('body') === 'setup_expired') {
        step.value = 'password'
        passwordError.value = 'The setup took too long. Start again.'
      } else {
        say(error)
      }
    } finally {
      busy.value = false
    }
  }

  function finish (): void {
    emit('changed')
    close()
  }
</script>
