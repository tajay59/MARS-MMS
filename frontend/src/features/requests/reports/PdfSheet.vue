<template>
  <ModalSheet v-model="open" labelledby="pdf-sheet-h" max-width="880" sheet>
    <div class="flex items-center gap-2">
      <h2 id="pdf-sheet-h" class="m-0 min-w-0 flex-1 truncate text-h3 text-surface-900">{{ title }}</h2>

      <v-btn
        v-if="link"
        color="primary"
        :download="link.filename"
        :href="link.url"
        :prepend-icon="mdiDownloadOutline"
        rel="noopener"
        variant="outlined"
      >Download</v-btn>

      <v-btn aria-label="Close" icon variant="text" @click="open = false"><v-icon :icon="mdiClose" /></v-btn>
    </div>

    <div v-if="state === 'loading'" aria-label="Opening the report…" class="flex h-[40dvh] items-center justify-center" role="status">
      <v-progress-circular color="primary" indeterminate size="28" />
    </div>

    <div v-else-if="state === 'failed'" class="flex h-[40dvh] flex-col items-center justify-center gap-3 text-center">
      <p class="m-0 max-w-[34ch] text-sm text-surface-700" role="alert">{{ problem }}</p>
      <v-btn variant="outlined" @click="load()">Try again</v-btn>
    </div>

    <div v-else-if="link" class="mt-2 flex h-[70dvh] min-h-0 flex-col overflow-hidden rounded-lg border border-surface-300">
      <PdfViewer :url="link.url" />
    </div>
  </ModalSheet>
</template>

<script lang="ts" setup>
  import { mdiClose, mdiDownloadOutline } from '@mdi/js'
  import { ref, watch } from 'vue'
  import ModalSheet from '@/components/ModalSheet.vue'
  import PdfViewer from '@/features/visits/viewers/PdfViewer.vue'

  // Any report of a request in the app's own PDF viewer (W18; never a new tab: an iPhone's tab
  // would show a blob or a download sheet). The ten-minute link is asked for each time the sheet
  // opens and never kept, because it acts as a password.
  const props = defineProps<{
    title: string
    fetchLink: () => Promise<{ url: string, filename: string } | null>
    /** What the last failed try said, for the retry panel. */
    reason?: string | null
  }>()

  const open = defineModel<boolean>({ required: true })

  const state = ref<'loading' | 'ready' | 'failed'>('loading')
  const link = ref<{ url: string, filename: string } | null>(null)
  const problem = ref('')

  async function load (): Promise<void> {
    state.value = 'loading'
    link.value = await props.fetchLink()
    if (link.value) {
      state.value = 'ready'
    } else {
      problem.value = props.reason ?? 'The report could not be opened. Try again.'
      state.value = 'failed'
    }
  }

  watch(open, isOpen => {
    if (isOpen) {
      void load()
    } else {
      link.value = null
    }
  })
</script>
