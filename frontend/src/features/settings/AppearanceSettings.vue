<template>
  <div class="flex max-w-xl flex-col gap-8">
    <section aria-labelledby="theme-h" class="flex flex-col gap-3">
      <div>
        <h2 id="theme-h" class="m-0 text-h3 text-surface-900">Theme</h2>
        <p class="m-0 text-sm text-surface-600">Saved on your account, so it follows you to every device. Everyone chooses their own in My profile.</p>
      </div>

      <AppearanceToggle labelledby="theme-h" />
    </section>

    <section aria-labelledby="motion-h" class="flex flex-col gap-3 border-t border-surface-200 pt-6">
      <div>
        <h2 id="motion-h" class="m-0 text-h3 text-surface-900">Animations</h2>
        <p class="m-0 text-sm text-surface-600">Pages, the list and the rail move as they change. Turn this off on this device if the motion is distracting. It is always off when the device asks for reduced motion.</p>
      </div>

      <div aria-labelledby="motion-h" class="grid grid-cols-2 overflow-hidden rounded-md border border-surface-500" role="radiogroup">
        <button
          v-for="(option, i) in MOTION"
          :key="option.value"
          :aria-checked="motionPreference === option.value"
          class="flex h-10 items-center justify-center text-sm font-medium"
          :class="[
            i === 1 ? 'border-l border-surface-500' : '',
            motionPreference === option.value ? 'bg-primary-50 font-semibold text-primary' : 'bg-surface text-surface-900 hover:bg-surface-100',
          ]"
          role="radio"
          type="button"
          @click="setMotionPreference(option.value)"
        >{{ option.label }}</button>
      </div>
    </section>
  </div>
</template>

<script lang="ts" setup>
  import { motionPreference, setMotionPreference } from '@/app/motion'
  import AppearanceToggle from '@/components/AppearanceToggle.vue'

  // The admin's own appearance (DBD D2) and, on this device, whether things animate (W4-10).
  const MOTION = [
    { value: 'system', label: 'On' },
    { value: 'reduced', label: 'Off' },
  ] as const
</script>
