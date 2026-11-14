<template>
  <PageBody
    :back="backTo"
    back-label="Back to the request"
    title="Review the work"
  >
    <template v-if="detail" #subtitle>
      <span class="font-mono" translate="no">{{ detail.ref }}</span>
      <RequestStatusChip :status="detail.status" />
      <span v-if="state?.kind === 'open'" class="min-w-0">{{ waitingText(state.waited) }}<template v-if="detail.auto_close_at"> · closes by itself on {{ formatDate(detail.auto_close_at) }}</template></span>
    </template>

    <div v-if="!loaded" aria-label="Opening the review…" class="flex justify-center py-16" role="status">
      <v-progress-circular color="primary" indeterminate size="28" />
    </div>

    <div v-else-if="missing || !detail" class="flex flex-col items-start gap-3 py-8">
      <h2 class="m-0 text-h3 text-surface-900">Request not found</h2>
      <p class="m-0 max-w-[48ch] text-surface-700">It may have been removed, or the link is not complete.</p>
      <v-btn color="primary" :to="{ name: 'requests' }">Go to requests</v-btn>
    </div>

    <div v-else class="flex flex-col gap-6">
      <div aria-live="polite" class="flex flex-col gap-3 empty:hidden">
        <FeedbackBanner v-if="!online" :icon="mdiWifiOff" type="warning">
          <b class="font-semibold">This needs a connection.</b> Reviewing and signing are done online. Reconnect, then try again.
        </FeedbackBanner>

        <FeedbackBanner v-if="failure" :type="failure.tone">
          <b class="font-semibold">{{ failure.title }}</b> {{ failure.text }}
          <div v-if="failure.reload" class="mt-2"><v-btn size="small" variant="outlined" @click="load()">Show the new reports</v-btn></div>
        </FeedbackBanner>

        <!-- After the answer went through -->
        <FeedbackBanner v-if="answered === 'accepted'" type="success">
          <b class="font-semibold">Work accepted.</b> The request is closed. Your close-out report is being made.
          <div class="mt-2"><v-btn size="small" :to="{ name: 'requests', params: { id: detail.id }, query: { tab: 'reports' } }" variant="outlined">See the reports</v-btn></div>
        </FeedbackBanner>

        <FeedbackBanner v-else-if="answered === 'rejected'" type="info">
          <b class="font-semibold">Sent back.</b> The technicians have been told and will contact you if they need more.
          <div class="mt-2"><v-btn size="small" :to="backTo" variant="outlined">Back to the request</v-btn></div>
        </FeedbackBanner>

        <FeedbackBanner v-else-if="notice" :type="notice.tone">
          <b class="font-semibold">{{ notice.title }}</b> {{ notice.text }}
          <div class="mt-2"><v-btn size="small" :to="backTo" variant="outlined">Back to the request</v-btn></div>
        </FeedbackBanner>
      </div>

      <template v-if="open || answered">
        <section aria-labelledby="rv-vr-h" class="flex flex-col gap-2">
          <h2 id="rv-vr-h" class="m-0 text-h3 text-surface-900">Visit reports</h2>

          <p v-if="visitReports.length === 0" class="m-0 text-sm text-surface-600">No visit reports are shown here.</p>

          <ul v-else class="m-0 flex list-none flex-col p-0">
            <li v-for="row in visitReports" :key="row.visitId" class="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 border-t border-surface-200 py-3 first:border-t-0">
              <span class="flex min-w-0 flex-col">
                <span>
                  <span class="font-mono text-sm font-medium" translate="no">{{ row.report?.number ?? row.ref }}</span>

                  <span v-if="row.report" class="ml-2 inline-flex items-center gap-1 rounded-full border border-success bg-success-container px-2 py-0.5 text-xs font-medium text-on-success-container">
                    <v-icon :icon="mdiCheck" size="12" />Final {{ versionText(row.report) }}
                  </span>
                </span>

                <span class="text-sm text-surface-600">{{ row.report?.finalized_at ? `Finalized ${formatDateTime(row.report.finalized_at)}` : 'The report is not final yet' }}</span>
              </span>

              <span v-if="row.report" class="flex items-center gap-1">
                <v-btn :prepend-icon="mdiFileOutline" size="small" variant="outlined" @click="openVisit(row.report)">Open</v-btn>
                <v-btn size="small" variant="text" @click="downloadVisit(row.report)">Download</v-btn>
              </span>
            </li>
          </ul>
        </section>

        <section v-if="clientReports.length > 0" aria-labelledby="rv-cr-h" class="flex flex-col gap-2">
          <h2 id="rv-cr-h" class="m-0 text-h3 text-surface-900">Your reports</h2>

          <ul class="m-0 flex list-none flex-col p-0">
            <li v-for="c in clientReports" :key="c.id" class="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 border-t border-surface-200 py-3 first:border-t-0">
              <span class="flex min-w-0 flex-col">
                <span class="wrap-break-word font-medium text-surface-900">{{ c.title }}</span>
                <span class="text-sm text-surface-600">{{ kindLabel(c.kind) }} · {{ clientReportSub(c, formatPlainDate) }}</span>
              </span>

              <v-btn v-if="clientReportLook(c) === 'file' || clientReportLook(c) === 'ready'" size="small" variant="outlined" @click="openClient(c)">Open</v-btn>
              <span v-else class="text-sm text-surface-600">Making the PDF</span>
            </li>
          </ul>
        </section>
      </template>

      <!-- The two answers (clients only; the request must still be in Client Review) -->
      <div v-if="open && !answered" class="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-surface-200 bg-surface-50 px-4 py-3">
        <span class="min-w-0 max-w-[52ch] text-sm text-surface-700">You are answering for {{ detail.org_name ?? 'your organization' }}. The first answer closes the review.</span>

        <div class="flex flex-wrap gap-2 max-md:w-full max-md:flex-col">
          <v-btn :block="!mdAndUp" :disabled="!online" variant="outlined" @click="rejecting = true">Reject</v-btn>
          <v-btn :block="!mdAndUp" color="primary" :disabled="!online" @click="accepting = true">Accept work</v-btn>
        </div>
      </div>
    </div>

    <SignDialog
      v-if="detail"
      v-model="accepting"
      :attestation="detail.attestation ?? ''"
      :busy="busy === 'accept'"
      :failure="failure ? `${failure.title} ${failure.text}` : null"
      submit-label="Sign and accept"
      :subtitle="`${detail.ref} · ${detail.title}`"
      :suggest="session.user?.name ?? ''"
      title="Accept the work"
      with-comment
      @sign="onAccept"
    />

    <RejectDialog v-model="rejecting" :busy="busy === 'reject'" :failure="failure" @send="onReject" />
    <PdfSheet v-model="sheet.opened.value" :fetch-link="sheet.fetchLink" :reason="sheet.reason.value" :title="sheet.title.value" />
  </PageBody>
</template>

<script lang="ts" setup>
  import type { ClientReportOut, ReportSummary } from '@/api/models'
  import { mdiCheck, mdiFileOutline, mdiWifiOff } from '@mdi/js'
  import { computed, ref, watch } from 'vue'
  import { useRoute } from 'vue-router'
  import { useDisplay } from 'vuetify'
  import { clientReportsApi } from '@/api/operations'
  import { reportsApi } from '@/api/report'
  import { useOnline } from '@/app/composables/useOnline'
  import { formatDate, formatDateTime, formatPlainDate } from '@/app/format'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import PageBody from '@/components/PageBody.vue'
  import RequestStatusChip from '@/components/RequestStatusChip.vue'
  import PdfSheet from '@/features/requests/reports/PdfSheet.vue'
  import { clientReportLook, clientReportSub, kindLabel, linkProblem } from '@/features/requests/reports/reports'
  import { useReportSheet } from '@/features/requests/reports/useReportSheet'
  import SignDialog from '@/features/visits/report/editor/SignDialog.vue'
  import { versionText } from '@/features/visits/report/words'
  import { useSessionStore } from '@/stores/session'
  import RejectDialog from './RejectDialog.vue'
  import { waitingText } from './review'
  import { useReview } from './useReview'

  // The review page of /requests/:id/review (PRD REQ-12, REQ-13; AFD J8; W18 boards 1 to 3): what
  // the client needs to decide, and the two answers. Accept is the signature dialog of W17 with the
  // client's own wording; Reject asks only for a reason. Both need a connection (OFF-10) and keep
  // nothing on the device. The server's answer decides what the page shows next.
  const route = useRoute()
  const session = useSessionStore()
  const online = useOnline()
  const { mdAndUp } = useDisplay()
  const sheet = useReportSheet()
  const requestId = computed(() => String(route.params.id))
  const backTo = computed(() => ({ name: 'requests', params: { id: requestId.value } }))

  const { detail, loaded, missing, visitReports, clientReports, busy, failure, answered, state, notice, open, load, accept, reject } = useReview(() => requestId.value)

  const accepting = ref(false)
  const rejecting = ref(false)

  async function onAccept (name: string, image: string, comment: string): Promise<void> {
    if (await accept(name, image, comment)) {
      accepting.value = false
    }
  }

  async function onReject (reason: string): Promise<void> {
    if (await reject(reason)) {
      rejecting.value = false
    }
  }

  function openVisit (report: ReportSummary): void {
    sheet.show(`${report.number} ${versionText(report)}`, () => reportsApi.download(report.id))
  }

  function openClient (report: ClientReportOut): void {
    sheet.show(report.title, () => report.kind === 'pdf' || !report.report_id
      ? clientReportsApi.download(report.id)
      : reportsApi.download(report.report_id))
  }

  async function downloadVisit (report: ReportSummary): Promise<void> {
    try {
      const { url, filename } = await reportsApi.download(report.id)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.rel = 'noopener'
      a.click()
    } catch (error) {
      sheet.reason.value = linkProblem(error)
    }
  }

  // A banner that closed the dialogs: an answer the server refused for a changed review
  watch(failure, value => {
    if (value?.reload) {
      accepting.value = false
      rejecting.value = false
    }
  })

  watch(requestId, () => void load(), { immediate: true })
</script>
