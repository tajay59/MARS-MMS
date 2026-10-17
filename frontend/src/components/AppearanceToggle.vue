<template>
  <div :aria-labelledby="labelledby" class="grid grid-cols-3 overflow-hidden rounded-md border border-surface-500" role="radiogroup">
    <button
      v-for="(option, i) in options"
      :key="option.value"
      :aria-checked="preference === option.value"
      class="flex items-center justify-center gap-2 font-medium"
      :class="[
        i === 1 ? 'border-x border-surface-500' : '',
        preference === option.value ? 'bg-primary-50 font-semibold text-primary' : 'bg-surface text-surface-900 hover:bg-surface-100',
        large ? 'h-12 text-base' : 'h-10 text-sm',
      ]"
      role="radio"
      type="button"
      @click="choose(option.value)"
    >
      <v-icon :icon="option.icon" size="18" />{{ option.label }}
    </button>
  </div>
</template>

<script lang="ts" setup>
  import { useAppearance } from '@/app/composables/useAppearance'
  import { icons } from '@/app/theme/icons'

  // Light / Dark / System (DBD D2), saved on the account.
  defineProps<{ labelledby: string, large?: boolean }>()

  const { preference, choose } = useAppearance()
  const options = [
    { value: 'light', label: 'Light', icon: icons.themeLight },
    { value: 'dark', label: 'Dark', icon: icons.themeDark },
    { value: 'system', label: 'System', icon: icons.themeSystem },
  ] as const
</script>
