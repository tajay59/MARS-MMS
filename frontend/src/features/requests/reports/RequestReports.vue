<template>
  <div class="flex flex-col gap-8">
    <FeedbackBanner v-if="problem" type="error">
      {{ problem }}
      <v-btn class="ml-2" size="small" variant="text" @click="reload()">Try again</v-btn>
    </FeedbackBanner>

    <div v-if="!loaded" aria-label="Loading the reports…" class="flex flex-col gap-3" role="status">
      <v-skeleton-loader type="heading, list-item-two-line, list-item-two-line" />
    </div>

    <template v-else>
      <!-- The close-out: the version in force leads, the replaced ones follow (W18-12) -->
      <section v-if="closeouts.current || pending" aria-labelledby="rr-co-h" class="flex flex-col gap-3">
        <div class="flex items-baseline justify-between gap-3">
          <h2 id="rr-co-h" class="m-0 text-h3 text-surface-900">Close-out report</h2>

          <span v-if="closeouts.current" class="inline-flex items-center gap-1 rounded-full border border-success bg-success-container px-2 py-0.5 text-xs font-medium text-on-success-container">
            <v-icon :icon="mdiCheck" size="12" />Final {{ versionText(closeouts.current) }}
          </span>
        </div>

        <div v-if="closeouts.current" class="flex flex-col gap-3 rounded-lg bg-surface-50 px-3.5 py-3">
          <dl class="m-0 grid grid-cols-[100px_minmax(0,1fr)] gap-x-3 gap-y-1 text-sm">
            <dt class="text-surface-600">Number</dt>
            <dd class="m-0 font-mono text-xs" translate="no">{{ closeouts.current.number }}</dd>
            <dt class="text-surface-600">Made</dt>
            <dd class="m-0">{{ formatDateTime(closeouts.current.finalized_at) }}</dd>
            <dt class="text-surface-600">Verification</dt>
            <dd class="m-0 break-all font-mono text-xs text-surface-700" translate="no">{{ shortHash(closeouts.current.pdf_sha256) }}</dd>
          </dl>

          <p v-if="!online" class="m-0 text-sm text-surface-700">Needs a connection. A report is read online only.</p>

          <div v-else class="flex flex-wrap gap-2 max-md:flex-col">
            <v-btn :block="!mdAndUp" color="primary" :prepend-icon="mdiFileOutline" @click="openReport(closeouts.current)">Open report</v-btn>

            <v-btn
              :block="!mdAndUp"
              :loading="saving === closeouts.current.id"
              :prepend-icon="mdiDownloadOutline"
              variant="outlined"
              @click="download(closeouts.current)"
            >Download PDF</v-btn>
          </div>
        </div>

        <div v-else class="flex items-center gap-3 rounded-lg bg-surface-50 px-3.5 py-3 text-sm text-surface-700" role="status">
          <v-progress-circular indeterminate size="16" width="2" />
          Being made. This usually takes under a minute.
        </div>

        <ul v-if="closeouts.replaced.length > 0" aria-label="Replaced close-out reports" class="m-0 flex list-none flex-col p-0">
          <li v-for="old in closeouts.replaced" :key="old.id" class="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 border-t border-surface-200 py-2.5 first:border-t-0">
            <span class="flex min-w-0 flex-col">
              <span class="text-surface-700">
                Close-out report
                <span class="ml-1 inline-flex items-center rounded-full border border-surface-400 bg-surface-100 px-2 py-0.5 text-xs font-medium text-surface-700">Replaced {{ versionText(old) }}</span>
              </span>

              <span class="text-sm text-surface-600">Made {{ formatDateTime(old.finalized_at) }}</span>
            </span>

            <v-btn v-if="online" size="small" variant="outlined" @click="openReport(old)">Open</v-btn>
          </li>
        </ul>
      </section>

      <!-- The report of each visit -->
      <section v-if="visitReports.length > 0" aria-labelledby="rr-vr-h" class="flex flex-col gap-2">
        <h2 id="rr-vr-h" class="m-0 text-h3 text-surface-900">Visit reports</h2>

        <ul class="m-0 flex list-none flex-col p-0">
          <li v-for="r in visitReports" :key="r.id" class="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 border-t border-surface-200 py-2.5 first:border-t-0">
            <span class="flex min-w-0 flex-col">
              <span>
                <span class="font-mono text-sm font-medium" translate="no">{{ r.number }}</span>

                <span class="ml-2 inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium" :class="chipOf(r)">
                  <v-icon v-if="r.status === 'final'" :icon="mdiCheck" size="12" />{{ statusText(r.status) }} {{ versionText(r) }}
                </span>
              </span>

              <span class="text-sm text-surface-600">{{ r.finalized_at ? `Finalized ${formatDateTime(r.finalized_at)}` : 'Not final yet' }}</span>
            </span>

            <span class="flex items-center gap-1">
              <v-btn v-if="!isClient && r.status !== 'final' && r.status !== 'superseded'" size="small" :to="{ name: 'visit-report', params: { id: r.id } }" variant="outlined">Open the editor</v-btn>
              <v-btn v-else-if="online" size="small" variant="outlined" @click="openReport(r)">Open</v-btn>
            </span>
          </li>
        </ul>
      </section>

      <!-- The client's own reports (CRP-5) -->
      <section aria-labelledby="rr-cr-h" class="flex flex-col gap-2">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <h2 id="rr-cr-h" class="m-0 text-h3 text-surface-900">Client reports</h2>

          <v-btn
            v-if="canAdd"
            :prepend-icon="mdiPlus"
            :to="{ name: 'client-report-new', params: { id: requestId } }"
            variant="outlined"
          >Add a client report</v-btn>
        </div>

        <p v-if="clientReports.length === 0" class="m-0 text-sm text-surface-600">
          {{ isClient ? 'Nothing added yet. Add your own report as a PDF or an online form.' : 'The client has not added a report.' }}
        </p>

        <ul v-else class="m-0 flex list-none flex-col p-0">
          <li v-for="c in clientReports" :key="c.id" class="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 border-t border-surface-200 py-2.5 first:border-t-0">
            <span class="flex min-w-0 flex-col">
              <span class="min-w-0">
                <span class="wrap-break-word font-medium text-surface-900">{{ c.title || 'Untitled report' }}</span>

                <span class="ml-2 inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium" :class="look(c) === 'draft' ? 'border-warning bg-warning-container text-on-warning-container' : 'border-surface-400 bg-surface-100 text-surface-700'">
                  {{ look(c) === 'draft' ? 'Draft' : kindLabel(c.kind) }}
                </span>

                <span v-if="look(c) === 'making'" class="ml-2 inline-flex items-center gap-1.5 rounded-full border border-info bg-info-container px-2 py-0.5 text-xs font-medium text-on-info-container">
                  <v-progress-circular indeterminate size="12" width="2" />Making the PDF
                </span>

                <span v-else-if="look(c) === 'failed'" class="ml-2 inline-flex items-center rounded-full border border-error bg-error-container px-2 py-0.5 text-xs font-medium text-on-error-container">PDF not made</span>
              </span>

              <span class="text-sm text-surface-600">{{ clientReportSub(c, formatPlainDate) }}</span>

              <span v-if="look(c) === 'failed'" class="mt-1 text-sm text-surface-700">
                {{ c.can_edit || isAuthor(c) ? 'The report was sent and is kept as you wrote it. Try again to make the PDF.' : 'The PDF could not be made. The client can try again.' }}
              </span>
            </span>

            <span class="flex items-center gap-1">
              <v-btn
                v-if="look(c) === 'draft' && c.can_edit"
                size="small"
                :to="{ name: 'client-report-draft', params: { id: requestId, reportId: c.id } }"
                variant="outlined"
              >Continue draft</v-btn>

              <v-btn
                v-else-if="look(c) === 'failed' && isAuthor(c)"
                :loading="retrying === c.id"
                size="small"
                variant="outlined"
                @click="tryAgain(c)"
              >Try again</v-btn>

              <v-btn v-else-if="online && (look(c) === 'file' || look(c) === 'ready')" size="small" variant="outlined" @click="openClient(c)">Open</v-btn>
            </span>
          </li>
        </ul>
      </section>
    </template>

    <PdfSheet v-model="sheet.opened.value" :fetch-link="sheet.fetchLink" :reason="sheet.reason.value" :title="sheet.title.value" />
  </div>
</template>

<script lang="ts" setup>
  import type { ClientReportOut, ReportSummary, RequestDetail } from '@/api/models'
  import { mdiCheck, mdiDownloadOutline, mdiFileOutline, mdiPlus } from '@mdi/js'
  import { storeToRefs } from 'pinia'
  import { computed, ref, watch } from 'vue'
  import { useDisplay } from 'vuetify'
  import { clientReportsApi } from '@/api/operations'
  import { reportsApi } from '@/api/report'
  import { useOnline } from '@/app/composables/useOnline'
  import { formatDateTime, formatPlainDate } from '@/app/format'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import { statusText, versionText } from '@/features/visits/report/words'
  import { useSessionStore } from '@/stores/session'
  import PdfSheet from './PdfSheet.vue'
  import { canAddClientReport, clientReportLook, clientReportSub, kindLabel, linkProblem } from './reports'
  import { useReportSheet } from './useReportSheet'
  import { useRequestReports } from './useRequestReports'

  // The Reports tab of a request (PRD RPT-8, CRP-5; AFD J8, J9; W18 board 4): the close-out report
  // first, then each visit's report, then the client's own. A client reads final reports only (the
  // server filters, rule 6) and adds their own; staff read all and also see a draft's editor link.
  // Reading is online only (OFF-10): nothing is kept on the device.
  const props = defineProps<{ detail: RequestDetail, isClient: boolean, refreshKey?: number }>()
  const emit = defineEmits<{ count: [n: number] }>()

  const online = useOnline()
  const { mdAndUp } = useDisplay()
  const session = useSessionStore()
  const { user } = storeToRefs(session)
  const sheet = useReportSheet()
  const saving = ref<string | null>(null)
  const retrying = ref<string | null>(null)

  const requestId = computed(() => props.detail.id)
  const canAdd = computed(() => props.isClient && canAddClientReport(props.detail.status))
  const { closeouts, visitReports, clientReports, loaded, problem, pending, count, reload } = useRequestReports(() => props.detail)

  const look = clientReportLook

  function shortHash (sha: string | null | undefined): string {
    return sha ? `${sha.slice(0, 16)}…${sha.slice(-8)}` : '—'
  }

  function isAuthor (report: ClientReportOut): boolean {
    return !!user.value && report.submitted_by?.id === user.value.id
  }

  function chipOf (report: ReportSummary): string {
    switch (report.status) {
      case 'final': {
        return 'border-success bg-success-container text-on-success-container'
      }
      case 'superseded': {
        return 'border-surface-400 bg-surface-100 text-surface-700'
      }
      default: {
        return 'border-warning bg-warning-container text-on-warning-container'
      }
    }
  }

  function openReport (report: ReportSummary): void {
    sheet.show(`${report.number} ${versionText(report)}`, () => reportsApi.download(report.id))
  }

  function openClient (report: ClientReportOut): void {
    sheet.show(report.title || 'Client report', () => report.kind === 'pdf' || !report.report_id
      ? clientReportsApi.download(report.id)
      : reportsApi.download(report.report_id))
  }

  async function download (report: ReportSummary): Promise<void> {
    saving.value = report.id
    try {
      const { url, filename } = await reportsApi.download(report.id)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.rel = 'noopener'
      a.click()
    } catch (error) {
      sheet.reason.value = linkProblem(error)
    } finally {
      saving.value = null
    }
  }

  // Try again: the same report is sent for drawing once more and nothing about it changes
  async function tryAgain (report: ClientReportOut): Promise<void> {
    retrying.value = report.id
    try {
      await clientReportsApi.submit(report.id)
    } finally {
      retrying.value = null
      await reload()
    }
  }

  watch(count, n => emit('count', n), { immediate: true })
  watch(() => props.refreshKey, () => void reload())
</script>
