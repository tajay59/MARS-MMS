<template>
  <div class="flex flex-col gap-2">
    <label :id="`${id}-label`" class="text-label text-surface-900" :for="id">{{ label }}</label>

    <v-otp-input
      :id="id"
      v-model="model"
      :aria-describedby="hint ? `${id}-hint` : undefined"
      :autofocus="autofocus"
      class="otp-field"
      :disabled="disabled"
      :error="error"
      :label="label"
      :length="6"
      variant="solo-inverted"
    />

    <p v-if="hint" :id="`${id}-hint`" class="m-0 text-sm text-surface-600">{{ hint }}</p>
  </div>
</template>

<script lang="ts" setup>
  // The 6-digit code from the authenticator app (W22). Vuetify's own code field: one real input
  // behind six boxes, so `autocomplete="one-time-code"`, the numeric keypad, paste and a phone's
  // "from messages" suggestion all work.
  defineProps<{
    id: string
    label: string
    hint?: string
    error?: boolean
    disabled?: boolean
    autofocus?: boolean
  }>()

  const model = defineModel<string>({ required: true })
</script>
