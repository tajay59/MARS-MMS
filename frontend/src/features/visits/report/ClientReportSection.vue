<template>
  <section v-if="report" aria-labelledby="crs-h" class="flex flex-col gap-2">
    <div class="flex items-baseline justify-between gap-3">
      <h2 id="crs-h" class="m-0 text-h3 text-surface-900">Report</h2>

      <span class="text-sm text-surface-600">
        <span class="font-mono" translate="no">{{ report.number }}</span> · {{ versionText(report) }}
      </span>
    </div>

    <div class="flex flex-col gap-3 rounded-lg bg-surface-50 px-3.5 py-3">
      <div class="flex items-center gap-2">
        <span class="inline-flex items-center gap-1 rounded-full border border-success bg-success-container px-2 py-0.5 text-xs font-medium text-on-success-container">
          <v-icon :icon="mdiCheck" size="12" />Final {{ versionText(report) }}
        </span>
      </div>

      <dl class="m-0 grid grid-cols-[100px_1fr] gap-x-3 gap-y-1 text-sm">
        <dt class="text-surface-600">Finalized</dt>
        <dd class="m-0">{{ finalized }}</dd>
        <dt class="text-surface-600">Verification</dt>
        <dd class="m-0 font-mono text-xs break-all">{{ report.pdf_sha256 }}</dd>
      </dl>

      <p v-if="!online" class="m-0 text-sm text-surface-700">Needs a connection. A report is read online only.</p>
      <p v-else-if="problem" class="m-0 text-sm text-error" role="alert">{{ problem }}</p>

      <div v-if="online" class="flex flex-wrap gap-2 max-md:flex-col">
        <v-btn :block="!mdAndUp" color="primary" :prepend-icon="mdiFileOutline" @click="opened = true">Open report</v-btn>

        <v-btn
          :block="!mdAndUp"
          :loading="saving"
          :prepend-icon="mdiDownloadOutline"
          variant="outlined"
          @click="download()"
        >Download PDF</v-btn>
      </div>
    </div>

    <ReportPreviewDialog v-model="opened" :fetch-link="link" :reason="problem" :report="report" />
  </section>
</template>

<script lang="ts" setup>
  import type { ReportSummary } from '@/api/models'
  import { mdiCheck, mdiDownloadOutline, mdiFileOutline } from '@mdi/js'
  import { computed, onBeforeUnmount, ref, watch } from 'vue'
  import { useDisplay } from 'vuetify'
  import { reportsApi } from '@/api/report'
  import { useOnline } from '@/app/composables/useOnline'
  import { formatWhen } from '../visits'
  import ReportPreviewDialog from './ReportPreviewDialog.vue'
  import { wordsFor } from './useVisitReport'
  import { versionText } from './words'

  // A client's Report section on an ended visit (W17-13): the final report of their own
  // organization, to read and download. The server returns final reports only, so a draft, a
  // superseded version and a correction in progress never show here (rule 6). Nothing is kept on
  // the device and the ten-minute link is asked for each time.
  const props = defineProps<{ visitId: string, zone?: string | null }>()

  const online = useOnline()
  const { mdAndUp } = useDisplay()
  const report = ref<ReportSummary | null>(null)
  const opened = ref(false)
  const saving = ref(false)
  const problem = ref<string | null>(null)
  let generation = 0

  const finalized = computed(() => report.value?.finalized_at ? formatWhen(report.value.finalized_at, props.zone ?? undefined) : '')

  async function load (): Promise<void> {
    const mine = ++generation
    try {
      const found = await reportsApi.list(`visit:${props.visitId}`)
      if (mine === generation) {
        report.value = found.find(r => r.status === 'final') ?? null
      }
    } catch {
      // Nothing to show is the same as nothing yet
    }
  }

  async function link (): Promise<{ url: string, filename: string } | null> {
    if (!report.value) {
      return null
    }
    problem.value = null
    try {
      const { url, filename } = await reportsApi.download(report.value.id)
      return { url, filename }
    } catch (error) {
      problem.value = wordsFor(error)
      return null
    }
  }

  async function download (): Promise<void> {
    saving.value = true
    const found = await link()
    saving.value = false
    if (found) {
      const a = document.createElement('a')
      a.href = found.url
      a.download = found.filename
      a.rel = 'noopener'
      a.click()
    }
  }

  function onVisible (): void {
    if (document.visibilityState === 'visible') {
      void load()
    }
  }

  watch(() => props.visitId, () => {
    report.value = null
    void load()
  }, { immediate: true })

  document.addEventListener('visibilitychange', onVisible)
  onBeforeUnmount(() => {
    generation += 1
    document.removeEventListener('visibilitychange', onVisible)
  })
</script>
