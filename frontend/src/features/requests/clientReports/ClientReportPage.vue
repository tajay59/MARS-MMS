<template>
  <PageBody
    :back="backTo"
    back-label="Back to the request"
    title="Add a client report"
  >
    <template v-if="request" #subtitle>
      <span class="font-mono" translate="no">{{ request.ref }}</span>
      <span v-if="form.report.value" class="inline-flex items-center rounded-full border border-warning bg-warning-container px-2 py-0.5 text-xs font-medium text-on-warning-container">Draft</span>

      <span v-if="form.report.value && saveText" aria-live="polite" class="inline-flex items-center gap-1.5 text-xs" :class="form.saveState.value === 'retrying' ? 'rounded-sm bg-warning-container px-2 py-0.5 text-on-warning-container' : 'text-surface-600'">
        <v-progress-circular v-if="form.saveState.value === 'saving' || form.saveState.value === 'retrying'" indeterminate size="12" width="2" />
        <v-icon v-else :icon="mdiCheck" size="14" />
        {{ saveText }}
      </span>
    </template>

    <div v-if="!form.loaded.value" aria-label="Opening the report…" class="flex justify-center py-16" role="status">
      <v-progress-circular color="primary" indeterminate size="28" />
    </div>

    <div v-else-if="form.missing.value || !request" class="flex flex-col items-start gap-3 py-8">
      <h2 class="m-0 text-h3 text-surface-900">Not found</h2>
      <p class="m-0 max-w-[48ch] text-surface-700">The request or the draft may have been removed, or the link is not complete.</p>
      <v-btn color="primary" :to="{ name: 'requests' }">Go to requests</v-btn>
    </div>

    <div v-else-if="form.gone.value" class="flex flex-col items-start gap-3 py-8">
      <h2 class="m-0 text-h3 text-surface-900">This report can’t be changed</h2>
      <p class="m-0 max-w-[48ch] text-surface-700">{{ form.problem.value ?? 'It was already sent, or this request cannot take a report now.' }} You can add another.</p>
      <v-btn color="primary" :to="backTo">Back to the request</v-btn>
    </div>

    <div v-else-if="!canAddClientReport(request.status)" class="flex flex-col items-start gap-3 py-8">
      <h2 class="m-0 text-h3 text-surface-900">This request can’t take a report yet</h2>
      <p class="m-0 max-w-[48ch] text-surface-700">You can add a report once the request has been approved.</p>
      <v-btn color="primary" :to="backTo">Back to the request</v-btn>
    </div>

    <div v-else class="flex flex-col gap-5">
      <div aria-live="polite" class="flex flex-col gap-3 empty:hidden">
        <FeedbackBanner v-if="!online" :icon="mdiWifiOff" type="warning">
          <b class="font-semibold">This needs a connection.</b> What you type stays on this page and is saved when the connection returns. Keep it open.
        </FeedbackBanner>

        <FeedbackBanner v-if="form.notice.value" type="info">{{ form.notice.value }}</FeedbackBanner>
        <FeedbackBanner v-if="form.problem.value" type="error">{{ form.problem.value }}</FeedbackBanner>
      </div>

      <!-- Step one: what kind of report -->
      <fieldset v-if="!form.report.value" class="m-0 flex min-w-0 flex-col gap-3 border-0 p-0">
        <legend class="mb-1 text-label text-surface-900">What kind of report is it?</legend>

        <div aria-label="Kind of report" class="grid gap-3 sm:grid-cols-2" role="group">
          <button
            v-for="option in kinds"
            :key="option.kind"
            class="flex min-w-0 flex-col items-start gap-1 rounded-card border border-surface-500 bg-surface px-4 py-3 text-left hover:bg-surface-50 focus-visible:outline-2 focus-visible:outline-primary"
            :disabled="starting"
            type="button"
            @click="choose(option.kind)"
          >
            <span class="flex items-center gap-2 font-medium text-surface-900"><v-icon :icon="option.icon" size="20" />{{ option.title }}</span>
            <span class="text-sm text-surface-700">{{ option.text }}</span>
          </button>
        </div>
      </fieldset>

      <!-- Step two: fill it in -->
      <div v-else class="grid min-w-0 gap-8 lg:grid-cols-[minmax(0,1fr)_280px]">
        <form class="flex min-w-0 flex-col gap-5" novalidate @submit.prevent="ask()">
          <p class="m-0 text-sm text-surface-700">
            {{ form.report.value.kind === 'pdf' ? 'Upload a PDF report you already have.' : 'Fill in the form. We make the PDF when you send it.' }}
          </p>

          <FormField id="cr-title" label="Title">
            <v-text-field
              id="cr-title"
              v-model="form.model.title"
              autocomplete="off"
              :error-messages="errors.title"
              :maxlength="TITLE_MAX"
              name="title"
            />
          </FormField>

          <FormField id="cr-date" label="Report date">
            <v-text-field
              id="cr-date"
              v-model="form.model.reportDate"
              autocomplete="off"
              class="max-w-56"
              name="report_date"
              type="date"
            />
          </FormField>

          <div class="flex flex-col gap-2">
            <span id="cr-stations-l" class="text-label text-surface-900">Stations covered</span>

            <div aria-labelledby="cr-stations-l" class="flex flex-wrap gap-1.5" role="group">
              <button
                v-for="s in request.stations"
                :key="s.id"
                :aria-pressed="form.model.stationIds.includes(s.id)"
                class="inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-sm"
                :class="form.model.stationIds.includes(s.id) ? 'border-primary bg-primary-50 text-primary-700 dark:text-primary' : 'border-surface-500 bg-surface text-surface-900'"
                type="button"
                @click="toggleStation(s.id)"
              >
                <v-icon v-if="form.model.stationIds.includes(s.id)" :icon="mdiCheck" size="14" />
                <span class="font-mono text-xs font-medium" translate="no">{{ s.code }}</span>
                {{ s.name }}
              </button>
            </div>

            <span class="text-xs text-surface-600">Only the stations on this request.</span>
            <p v-if="errors.stations" class="m-0 text-sm text-error" role="alert">{{ errors.stations }}</p>
          </div>

          <template v-if="form.report.value.kind === 'form'">
            <FormField id="cr-summary" label="Summary">
              <v-textarea
                id="cr-summary"
                v-model="form.model.summary"
                auto-grow
                autocomplete="off"
                :error-messages="errors.summary"
                :maxlength="SUMMARY_MAX"
                name="summary"
                rows="4"
              />

              <template #aside><span class="text-xs tabular-nums text-surface-600">{{ form.model.summary.length.toLocaleString('en-GB') }} of {{ SUMMARY_MAX.toLocaleString('en-GB') }}</span></template>
            </FormField>

            <FormField
              v-for="s in covered"
              :id="`cr-obs-${s.id}`"
              :key="s.id"
              :label="`${s.code} ${s.name}`"
            >
              <v-textarea
                :id="`cr-obs-${s.id}`"
                v-model="form.model.observations[s.id]"
                auto-grow
                autocomplete="off"
                :maxlength="OBSERVATION_MAX"
                :name="`observation_${s.code}`"
                placeholder="Anything you saw at this station (optional)"
                rows="2"
              />
            </FormField>

            <FormField id="cr-notes" label="Data quality">
              <v-textarea
                id="cr-notes"
                v-model="form.model.notes"
                auto-grow
                autocomplete="off"
                :maxlength="NOTES_MAX"
                name="data_quality_notes"
                placeholder="Gaps, bad readings or anything else the data users should know (optional)"
                rows="2"
              />
            </FormField>
          </template>

          <ClientReportFiles :error="errors.file" :files="files" :kind="form.report.value.kind" />

          <!-- Phones: the buttons come at the end of the form -->
          <div v-if="!mdAndUp" class="flex flex-col gap-2">
            <v-btn block color="primary" :disabled="!online" type="submit">Submit</v-btn>
            <v-btn block :disabled="!online" variant="outlined" @click="saveNow()">Save draft</v-btn>
          </div>
        </form>

        <aside v-if="mdAndUp" aria-label="Sending" class="flex flex-col gap-3 self-start rounded-lg border border-surface-200 px-4 py-3">
          <h2 class="m-0 text-h3 text-surface-900">Before you send</h2>
          <p class="m-0 text-sm text-surface-700">A sent report cannot be changed. If something is wrong, add a new report.</p>

          <div class="flex flex-wrap gap-2">
            <v-btn color="primary" :disabled="!online" @click="ask()">Submit</v-btn>
            <v-btn :disabled="!online" variant="outlined" @click="saveNow()">Save draft</v-btn>
          </div>

          <span class="text-xs text-surface-600">You can leave and come back: the draft is under Continue draft on the Reports tab.</span>
        </aside>
      </div>
    </div>

    <ModalSheet v-model="confirming" labelledby="cr-confirm-h" max-width="440" persistent>
      <div class="flex flex-col gap-4">
        <h2 id="cr-confirm-h" class="m-0 text-h3 text-surface-900">Submit this report?</h2>
        <p class="m-0 text-surface-700">“{{ form.model.title }}” goes to the technicians and your organization. You cannot change it afterwards.</p>

        <div class="flex flex-wrap justify-end gap-2">
          <v-btn :disabled="form.sending.value" variant="outlined" @click="confirming = false">Keep editing</v-btn>
          <v-btn color="primary" :loading="form.sending.value" @click="send()">Submit</v-btn>
        </div>
      </div>
    </ModalSheet>
  </PageBody>
</template>

<script lang="ts" setup>
  import type { ClientReportOut } from '@/api/models'
  import { mdiCheck, mdiFileDocumentEditOutline, mdiTrayArrowUp, mdiWifiOff } from '@mdi/js'
  import { computed, reactive, ref } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { useDisplay } from 'vuetify'
  import { useOnline } from '@/app/composables/useOnline'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import FormField from '@/components/FormField.vue'
  import ModalSheet from '@/components/ModalSheet.vue'
  import PageBody from '@/components/PageBody.vue'
  import { canAddClientReport } from '../reports/reports'
  import { NOTES_MAX, OBSERVATION_MAX, saveWords, SUMMARY_MAX, TITLE_MAX } from './clientReport'
  import ClientReportFiles from './ClientReportFiles.vue'
  import { useClientReportFiles } from './useClientReportFiles'
  import { useClientReportForm } from './useClientReportForm'

  // The client report page of /requests/:id/client-reports/new and .../:reportId (PRD CRP-1 to CRP-4;
  // AFD J9; W18 boards 5 and 6). The draft is made when a kind is chosen and saved as the person
  // types; Submit asks once more, and nothing changes the report afterwards. Online only (OFF-10).
  const route = useRoute()
  const router = useRouter()
  const online = useOnline()
  const { mdAndUp } = useDisplay()

  const requestId = computed(() => String(route.params.id))
  const reportId = computed(() => typeof route.params.reportId === 'string' ? route.params.reportId : null)
  const backTo = computed(() => ({ name: 'requests', params: { id: requestId.value }, query: { tab: 'reports' } }))

  const form = useClientReportForm(() => requestId.value)
  const { request } = form
  const files = useClientReportFiles(() => form.report.value, form)

  const kinds = [
    { kind: 'pdf' as const, title: 'Upload a PDF', text: 'You already have the report as a file.', icon: mdiTrayArrowUp },
    { kind: 'form' as const, title: 'Fill in the online form', text: 'We make the PDF for you.', icon: mdiFileDocumentEditOutline },
  ]

  // Where each thing that can be missing is on the page: the error it gets, and what to look at
  const POINT_AT: Record<string, { field: 'title' | 'stations' | 'summary' | 'file', selector: string, focus: boolean }> = {
    title: { field: 'title', selector: '#cr-title', focus: true },
    stations: { field: 'stations', selector: '#cr-stations-l', focus: false },
    summary: { field: 'summary', selector: '#cr-summary', focus: true },
    file: { field: 'file', selector: '[data-testid^="client-report"]', focus: false },
  }

  const starting = ref(false)
  const confirming = ref(false)
  const errors = reactive<{ title?: string, stations?: string, summary?: string, file?: string }>({})

  const saveText = computed(() => saveWords(form.saveState.value, form.savedAt.value))
  const covered = computed(() => (form.request.value?.stations ?? []).filter(s => form.model.stationIds.includes(s.id)))

  async function choose (kind: ClientReportOut['kind']): Promise<void> {
    starting.value = true
    await form.begin(kind)
    starting.value = false
  }

  function toggleStation (id: string): void {
    const at = form.model.stationIds.indexOf(id)
    if (at === -1) {
      // Keep the order of the request's stations
      const order = (form.request.value?.stations ?? []).map(s => s.id)
      form.model.stationIds = order.filter(i => i === id || form.model.stationIds.includes(i))
    } else {
      form.model.stationIds = form.model.stationIds.filter(i => i !== id)
    }
    errors.stations = undefined
  }

  function clearErrors (): void {
    errors.title = undefined
    errors.stations = undefined
    errors.summary = undefined
    errors.file = undefined
  }

  async function saveNow (): Promise<void> {
    await form.flush()
  }

  // Submit asks for confirmation once the report is complete; otherwise it points at what is missing
  function ask (): void {
    clearErrors()
    const problem = form.problemFor({ fileReady: files.pdfReady.value, filesBusy: files.busy.value })
    if (problem) {
      const found = POINT_AT[problem.field]
      if (found) {
        errors[found.field] = problem.text
        const target = document.querySelector<HTMLElement>(found.selector)
        target?.scrollIntoView({ block: 'center' })
        if (found.focus) {
          target?.focus()
        }
      }
      return
    }
    confirming.value = true
  }

  async function send (): Promise<void> {
    if (await form.submit()) {
      confirming.value = false
      await router.push(backTo.value)
    } else {
      confirming.value = false
    }
  }

  async function start (): Promise<void> {
    if (reportId.value) {
      await form.open(reportId.value)
      if (form.report.value) {
        await files.hold(form.report.value)
      }
    } else {
      await form.prepare()
    }
  }

  void start()
</script>
