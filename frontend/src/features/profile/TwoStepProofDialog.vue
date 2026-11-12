<template>
  <ModalSheet v-model="open" labelledby="ts-proof-h" :max-width="460" persistent>
    <!-- New recovery codes, shown once -->
    <div v-if="codes" class="flex flex-col gap-4">
      <div class="flex flex-col gap-2">
        <h2 id="ts-proof-h" class="m-0 text-h2 text-surface-900">Save your new recovery codes</h2>
        <p class="m-0 text-sm text-surface-900">The old codes no longer work. Keep these somewhere safe, such as a password manager.</p>
      </div>

      <RecoveryCodes :codes="codes" :email="email" @done="close" />
    </div>

    <form v-else class="flex flex-col gap-4" novalidate @submit.prevent="submit">
      <div class="flex flex-col gap-2">
        <h2 id="ts-proof-h" class="m-0 text-h2 text-surface-900">{{ mode === 'off' ? 'Turn off two-step sign-in?' : 'Make new recovery codes?' }}</h2>

        <p class="m-0 text-sm text-surface-900">
          {{ mode === 'off'
            ? 'You’ll log in with your password alone. Your other devices will be logged out. Your recovery codes stop working.'
            : 'The old codes stop working. Enter your password and a code to make new ones.' }}
        </p>
      </div>

      <FeedbackBanner v-if="problem" :type="problemType">{{ problem }}</FeedbackBanner>

      <PasswordField
        id="ts-proof-password"
        v-model="password"
        autocomplete="current-password"
        :error="passwordError"
        label="Password"
      />

      <FormField v-if="useRecovery" id="ts-proof-recovery" label="Recovery code">
        <v-text-field
          id="ts-proof-recovery"
          v-model="recovery"
          autocapitalize="characters"
          autocomplete="off"
          class="font-mono"
          hide-details
          name="recovery-code"
          spellcheck="false"
        />
      </FormField>

      <OtpField
        v-else
        id="ts-proof-code"
        v-model="code"
        :error="problemType === 'error' && Boolean(problem)"
        label="6-digit code from your app"
      />

      <button class="inline-flex min-h-6 items-center self-start text-sm font-medium text-primary" type="button" @click="swap">
        {{ useRecovery ? 'Use a code from my app instead' : 'Use a recovery code instead' }}
      </button>

      <div class="flex justify-end gap-2">
        <v-btn class="text-primary" variant="text" @click="close">{{ mode === 'off' ? 'Keep it on' : 'Cancel' }}</v-btn>
        <v-btn :color="mode === 'off' ? 'error' : 'primary'" :loading="busy" type="submit">{{ mode === 'off' ? 'Turn off' : 'Make new codes' }}</v-btn>
      </div>
    </form>
  </ModalSheet>
</template>

<script lang="ts" setup>
  import { computed, ref, watch } from 'vue'
  import { totpApi, type TotpFactor } from '@/api/auth'
  import { ApiError, NetworkError } from '@/api/problem'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import FormField from '@/components/FormField.vue'
  import ModalSheet from '@/components/ModalSheet.vue'
  import PasswordField from '@/components/PasswordField.vue'
  import OtpField from '@/features/auth/twoStep/OtpField.vue'
  import RecoveryCodes from '@/features/auth/twoStep/RecoveryCodes.vue'
  import { useSessionStore } from '@/stores/session'

  // Turning two-step sign-in off, or making new recovery codes (W22-7): both ask for the password
  // and a current code (or a recovery code), so a borrowed, unlocked laptop can't do either.
  const props = defineProps<{ mode: 'off' | 'codes' }>()
  const open = defineModel<boolean>({ required: true })
  const emit = defineEmits<{ changed: [] }>()

  const session = useSessionStore()
  const email = computed(() => session.user?.email ?? '')
  const password = ref('')
  const code = ref('')
  const recovery = ref('')
  const useRecovery = ref(false)
  const busy = ref(false)
  const problem = ref<string | null>(null)
  const problemType = ref<'error' | 'warning'>('error')
  const passwordError = ref<string | undefined>()
  const codes = ref<string[] | null>(null)

  watch(open, isOpen => {
    if (isOpen) {
      password.value = ''
      code.value = ''
      recovery.value = ''
      useRecovery.value = false
      problem.value = null
      passwordError.value = undefined
      codes.value = null
    }
  })

  function close (): void {
    open.value = false
  }

  function swap (): void {
    useRecovery.value = !useRecovery.value
    problem.value = null
    code.value = ''
    recovery.value = ''
  }

  async function submit (): Promise<void> {
    if (busy.value) {
      return
    }
    problem.value = null
    passwordError.value = undefined
    const factor: TotpFactor = useRecovery.value ? { recovery_code: recovery.value.trim() } : { code: code.value }
    if (!password.value) {
      passwordError.value = 'Enter your password.'
      return
    }
    if (useRecovery.value ? recovery.value.trim().length === 0 : code.value.length < 6) {
      problemType.value = 'error'
      problem.value = useRecovery.value ? 'Enter a recovery code.' : 'Enter the 6-digit code.'
      return
    }
    busy.value = true
    try {
      if (props.mode === 'off') {
        await totpApi.turnOff(password.value, factor)
        await session.reloadMe()
        emit('changed')
        close()
      } else {
        codes.value = (await totpApi.newRecoveryCodes(password.value, factor)).recovery_codes
        await session.reloadMe()
        emit('changed')
      }
      password.value = ''
    } catch (error) {
      code.value = ''
      recovery.value = ''
      explain(error)
    } finally {
      busy.value = false
    }
  }

  function explain (error: unknown): void {
    problemType.value = 'error'
    if (error instanceof NetworkError) {
      problem.value = 'This needs a connection. Try again when you have signal.'
    } else if (error instanceof ApiError && error.status === 429) {
      problemType.value = 'warning'
      problem.value = 'Too many attempts. Try again in 15 minutes.'
    } else if (error instanceof ApiError && error.fieldCode('password') === 'wrong_password') {
      passwordError.value = 'Password is incorrect.'
    } else if (error instanceof ApiError && (error.fieldCode('code') === 'wrong_code' || error.fieldCode('recovery_code') === 'wrong_code')) {
      problem.value = useRecovery.value
        ? 'That recovery code is incorrect or already used.'
        : 'That code is incorrect. Enter the current code from your app.'
    } else if (error instanceof ApiError && error.code === 'totp_required') {
      problem.value = 'Your role needs two-step sign-in, so it can’t be turned off.'
    } else {
      problem.value = 'Something went wrong on our side. Try again in a minute.'
    }
  }
</script>
