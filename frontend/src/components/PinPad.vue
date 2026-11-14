<template>
  <div aria-label="PIN" class="flex flex-col items-center gap-6" role="group">
    <div
      :aria-label="`${modelValue.length} ${modelValue.length === 1 ? 'digit' : 'digits'} entered`"
      class="flex justify-center gap-4"
      role="img"
    >
      <span
        v-for="n in MAX"
        :key="n"
        class="box-border size-4.5 rounded-full border-2"
        :class="n <= modelValue.length ? 'border-primary bg-primary' : error ? 'border-error' : 'border-surface-300'"
      />
    </div>

    <div class="grid w-full max-w-75 grid-cols-3 gap-3">
      <template v-for="key in keys" :key="key.label">
        <span v-if="key.blank" />

        <v-btn
          v-else-if="key.back"
          aria-label="Delete the last digit"
          :disabled="disabled || modelValue.length === 0"
          height="56"
          :icon="mdiBackspaceOutline"
          variant="text"
          @click="back"
        />

        <v-btn
          v-else
          class="text-2xl"
          :disabled="disabled"
          height="56"
          variant="tonal"
          @click="press(key.label)"
        >{{ key.label }}</v-btn>
      </template>
    </div>
  </div>
</template>

<script lang="ts" setup>
  import { mdiBackspaceOutline } from '@mdi/js'
  import { onBeforeUnmount, onMounted } from 'vue'

  // A number pad for the device PIN (AUTH-12): big targets, no on-screen keyboard to cover the
  // page, and the keyboard's digits, Backspace and Enter work on a computer. The model is the digits so far.
  const props = defineProps<{ disabled?: boolean, error?: boolean }>()
  const modelValue = defineModel<string>({ required: true })
  const emit = defineEmits<{ submit: [] }>()

  const MAX = 6
  const keys = [
    ...['1', '2', '3', '4', '5', '6', '7', '8', '9'].map(label => ({ label, blank: false, back: false })),
    { label: 'blank', blank: true, back: false },
    { label: '0', blank: false, back: false },
    { label: 'back', blank: false, back: true },
  ]

  function press (digit: string): void {
    if (!props.disabled && modelValue.value.length < MAX) {
      modelValue.value += digit
    }
  }

  function back (): void {
    modelValue.value = modelValue.value.slice(0, -1)
  }

  function onKey (event: KeyboardEvent): void {
    if (props.disabled || event.ctrlKey || event.metaKey || event.altKey) {
      return
    }
    if (/^\d$/.test(event.key)) {
      press(event.key)
    } else if (event.key === 'Backspace') {
      back()
    } else if (event.key === 'Enter') {
      emit('submit')
    }
  }

  onMounted(() => document.addEventListener('keydown', onKey))
  onBeforeUnmount(() => document.removeEventListener('keydown', onKey))
</script>
