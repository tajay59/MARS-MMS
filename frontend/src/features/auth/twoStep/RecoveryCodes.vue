<template>
  <div class="flex flex-col gap-4">
    <FeedbackBanner type="warning">
      <b class="font-semibold">We show these only once.</b> After you close this, they can’t be shown again. You can make new ones in My profile.
    </FeedbackBanner>

    <ul
      aria-label="Recovery codes"
      class="m-0 grid list-none grid-cols-1 gap-x-6 gap-y-2 rounded-md bg-surface-100 p-4 sm:grid-cols-2"
      role="list"
    >
      <li v-for="code in codes" :key="code" class="font-mono text-base tracking-wide text-surface-900">{{ code }}</li>
    </ul>

    <div class="flex flex-wrap gap-2">
      <v-btn :prepend-icon="copied ? mdiCheck : mdiContentCopy" variant="outlined" @click="copy">{{ copied ? 'Copied' : 'Copy codes' }}</v-btn>
      <v-btn :prepend-icon="mdiDownload" variant="outlined" @click="save">Download as text</v-btn>
    </div>

    <span aria-live="polite" class="sr-only">{{ copied ? 'Recovery codes copied.' : '' }}</span>

    <label class="flex min-h-12 cursor-pointer items-center gap-3">
      <input v-model="saved" class="size-5 accent-primary" type="checkbox">
      <span class="text-surface-900">I’ve saved my recovery codes</span>
    </label>

    <div class="flex justify-end border-t border-surface-200 pt-4">
      <v-btn color="primary" :disabled="!saved" @click="emit('done')">{{ doneLabel }}</v-btn>
    </div>
  </div>
</template>

<script lang="ts" setup>
  import { mdiCheck, mdiContentCopy, mdiDownload } from '@mdi/js'
  import { ref } from 'vue'
  import { formatDate } from '@/app/format'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import { recoveryCodesText } from './twoStep'

  // Ten one-time codes, shown once (W22-5): copy, download, and a tick before Done. No print
  // button: a file or a password manager keeps them safer than paper left in a printer tray.
  const props = withDefaults(defineProps<{
    codes: readonly string[]
    email: string
    doneLabel?: string
  }>(), { doneLabel: 'Done' })

  const emit = defineEmits<{ done: [] }>()
  const saved = ref(false)
  const copied = ref(false)

  async function copy (): Promise<void> {
    try {
      await navigator.clipboard.writeText(props.codes.join('\n'))
      copied.value = true
      setTimeout(() => {
        copied.value = false
      }, 3000)
    } catch {
      // No clipboard permission: they are on screen, and Download works
    }
  }

  function save (): void {
    const text = recoveryCodesText(props.codes, props.email, formatDate(new Date().toISOString()))
    const link = document.createElement('a')
    link.href = URL.createObjectURL(new Blob([text], { type: 'text/plain' }))
    link.download = 'mars-mms-recovery-codes.txt'
    link.click()
    setTimeout(() => URL.revokeObjectURL(link.href), 1000)
  }
</script>
