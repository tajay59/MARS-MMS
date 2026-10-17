<template>
  <FormField :id="id" :label="label">
    <template v-if="$slots.aside" #aside><slot name="aside" /></template>

    <v-text-field
      :id="id"
      v-model="model"
      :autocomplete="autocomplete"
      :error="Boolean(error)"
      hide-details
      :name="name"
      spellcheck="false"
      :type="shown ? 'text' : 'password'"
      v-bind="describedBy ? { 'aria-describedby': describedBy } : {}"
    >
      <template #append-inner>
        <button
          aria-label="Show password"
          :aria-pressed="shown"
          class="-mr-2 flex size-10 items-center justify-center rounded-md text-surface-600"
          type="button"
          @click="shown = !shown"
        >
          <v-icon :icon="shown ? mdiEyeOffOutline : mdiEyeOutline" size="20" />
        </button>
      </template>
    </v-text-field>

    <p
      v-if="error || hint"
      :id="describedBy"
      aria-live="polite"
      class="m-0 flex items-center gap-1.5 text-sm"
      :class="error ? 'text-on-error-container' : hintOk ? 'text-on-success-container' : 'text-surface-600'"
    >
      <v-icon v-if="error || hintOk" :icon="error ? mdiAlertCircleOutline : mdiCheck" size="16" />
      {{ error || hint }}
    </p>
  </FormField>
</template>

<script lang="ts" setup>
  import { mdiAlertCircleOutline, mdiCheck, mdiEyeOffOutline, mdiEyeOutline } from '@mdi/js'
  import { computed, ref } from 'vue'
  import FormField from './FormField.vue'

  // A password input with Show/Hide, and the rule or error under it (AUTH-1: 10 or more characters).
  const props = defineProps<{
    id: string
    label: string
    autocomplete: 'current-password' | 'new-password'
    name?: string
    error?: string
    hint?: string
    /** The hint is a rule the password now meets: shown in green with a tick. */
    hintOk?: boolean
  }>()

  const model = defineModel<string>({ required: true })
  const shown = ref(false)
  const describedBy = computed(() => (props.error || props.hint) ? `${props.id}-help` : undefined)
</script>
