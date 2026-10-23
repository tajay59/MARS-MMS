<template>
  <section aria-labelledby="install-h" class="flex flex-col gap-3 rounded-card bg-surface-50 p-4">
    <h2 id="install-h" class="m-0 text-h3 text-surface-900">Install {{ APP_NAME }} to prepare</h2>

    <p class="m-0 text-surface-900">
      On an iPhone, the app on your Home Screen keeps its own saved visits, separate from Safari. A visit prepared here would not be there. Install first, then prepare.
    </p>

    <ol class="m-0 flex list-none flex-col gap-3 p-0">
      <li v-for="(step, index) in steps" :key="step" class="flex items-start gap-3">
        <span aria-hidden="true" class="grid size-7 shrink-0 place-items-center rounded-full bg-primary text-sm font-bold text-on-primary">{{ index + 1 }}</span>
        <span class="text-surface-900">{{ step }}</span>
      </li>
    </ol>

    <p class="m-0 text-sm text-surface-600">Do this at the office, with signal.</p>
  </section>
</template>

<script lang="ts" setup>
  import { APP_NAME } from '@/app/brand'

  // Finding F2: an iPhone keeps the Home Screen app's storage apart from Safari's, and Safari tabs
  // are cleaned up after seven days. Prepare does nothing in a tab; this says why and what to do.
  const steps = [
    'Tap Share at the bottom of Safari.',
    'Scroll and tap Add to Home Screen, then Add.',
    `Open ${APP_NAME} from your Home Screen and log in again.`,
    'Open this visit and tap Prepare for field.',
  ]
</script>
