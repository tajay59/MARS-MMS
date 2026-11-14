<template>
  <ModalSheet v-model="open" labelledby="rp-h" max-width="880" sheet>
    <div class="flex items-center gap-2">
      <h2 id="rp-h" class="m-0 min-w-0 flex-1 truncate text-h3 text-surface-900">
        {{ report.status === 'draft' ? 'Draft' : 'Report' }} <span class="font-mono" translate="no">{{ report.number }}</span> {{ versionText(report) }}
      </h2>

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

    <div v-if="state === 'loading'" aria-label="Opening the draft…" class="flex h-[40dvh] items-center justify-center" role="status">
      <v-progress-circular color="primary" indeterminate size="28" />
    </div>

    <div v-else-if="state === 'failed'" class="flex h-[40dvh] flex-col items-center justify-center gap-3 text-center">
      <p class="m-0 max-w-[34ch] text-sm text-surface-700" role="alert">{{ problem }}</p>
      <v-btn variant="outlined" @click="load()">Try again</v-btn>
    </div>

    <template v-else-if="link">
      <p v-if="report.status === 'draft' && !report.pdf.current" class="m-0 mt-2 text-sm text-surface-700">This is an older drawing. Close this and choose Preview to draw the visit as it is now.</p>

      <div class="mt-2 flex h-[70dvh] min-h-0 flex-col overflow-hidden rounded-lg border border-surface-300">
        <PdfViewer :url="link.url" />
      </div>
    </template>
  </ModalSheet>
</template>

<script lang="ts" setup>
  import type { ReportSummary } from '@/api/models'
  import { mdiClose, mdiDownloadOutline } from '@mdi/js'
  import { ref, watch } from 'vue'
  import ModalSheet from '@/components/ModalSheet.vue'
  import PdfViewer from '../viewers/PdfViewer.vue'
  import { versionText } from './words'

  // The draft PDF in the app's own viewer (W16, RPT-3), never a new tab: an iPhone's tab would
  // show a blob or a download sheet. The link is asked for each time the sheet opens and never
  // kept, because it acts as a password for ten minutes.
  const props = defineProps<{
    report: ReportSummary
    fetchLink: () => Promise<{ url: string, filename: string } | null>
    reason: string | null
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
      problem.value = props.reason ?? 'The draft could not be opened. Try again.'
      state.value = 'failed'
    }
  }

  watch(open, isOpen => {
    if (isOpen) {
      void load()
    } else {
      link.value = null
    }
  }, { immediate: true })
</script>
