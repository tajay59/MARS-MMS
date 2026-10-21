<template>
  <span class="inline-flex flex-col items-start gap-0.5">
    <button
      class="inline-flex h-9 max-w-full items-center gap-2 rounded-lg bg-transparent pl-2.5 pr-3 text-left shadow-[inset_0_0_0_1px_currentColor] hover:bg-black/5 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
      :disabled="busy"
      type="button"
      @click="open"
    >
      <v-icon :icon="mdiFilePdfBox" size="20" />
      <span class="min-w-0 truncate font-mono text-xs font-medium" translate="no">{{ file.name }}</span>
      <span class="shrink-0 text-xs tabular-nums">{{ formatBytes(file.size_bytes) }}</span>
    </button>

    <span v-if="error" class="text-xs text-error" role="alert">{{ error }}</span>
  </span>
</template>

<script lang="ts" setup>
  import type { AttachmentOut } from '@/api/models'
  import { mdiFilePdfBox } from '@mdi/js'
  import { ref } from 'vue'
  import { ApiError, NetworkError } from '@/api/problem'
  import { formatBytes, openDownload } from '@/features/stations/documents'

  // A PDF already on a request or comment. The link is asked for on click and used at once; the
  // server answers 404 for a file the person may not see, so nothing here hides anything itself.
  const props = defineProps<{
    file: AttachmentOut
    link: () => Promise<{ url: string }>
  }>()

  const busy = ref(false)
  const error = ref<string | null>(null)

  async function open (): Promise<void> {
    busy.value = true
    error.value = null
    try {
      await openDownload(props.file.name, () => props.link())
    } catch (error_) {
      error.value = error_ instanceof NetworkError
        ? 'You’re offline. Try again when you have signal.'
        : (error_ instanceof ApiError && error_.code === 'not_ready' ? 'Still being checked. Try again in a moment.' : 'We couldn’t open that file.')
    } finally {
      busy.value = false
    }
  }
</script>
