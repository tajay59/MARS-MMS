<template>
  <PageBody
    :back="backTo"
    back-label="Back to the visit"
    title="Visit report"
    wide
  >
    <template v-if="report" #subtitle>
      <span class="font-mono" translate="no">{{ report.number }}</span>

      <span class="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium" :class="chip">
        <v-icon v-if="report.status === 'final'" :icon="mdiCheck" size="12" />{{ statusLabel(report) }}
      </span>

      <span v-if="request" class="min-w-0 truncate">{{ request }}</span>

      <span v-if="editable" aria-live="polite" class="inline-flex items-center gap-1.5 text-xs" :class="saveState === 'retrying' ? 'rounded-sm bg-warning-container px-2 py-0.5 text-on-warning-container' : 'text-surface-600'">
        <v-progress-circular v-if="saveState === 'saving' || saveState === 'retrying'" indeterminate size="12" width="2" />
        {{ saveWords }}
      </span>
    </template>

    <template v-if="report && online" #actions>
      <v-btn
        :loading="busy === 'preview'"
        :prepend-icon="mdiFileEyeOutline"
        variant="outlined"
        @click="preview()"
      >{{ editable ? 'Preview PDF' : 'Open PDF' }}</v-btn>
    </template>

    <div v-if="!loaded" aria-label="Opening the report…" class="flex justify-center py-16" role="status">
      <v-progress-circular color="primary" indeterminate size="28" />
    </div>

    <div v-else-if="notFound || !report" class="flex flex-col items-start gap-3 py-8">
      <h2 class="m-0 text-h3 text-surface-900">Report not found</h2>
      <p class="m-0 max-w-[48ch] text-surface-700">It may have been removed, or the link is not complete.</p>
      <v-btn color="primary" :to="{ name: 'visits' }">Go to visits</v-btn>
    </div>

    <div v-else class="flex flex-col gap-4">
      <!-- What the person needs to know first -->
      <div aria-live="polite" class="flex flex-col gap-3 empty:hidden">
        <FeedbackBanner v-if="!online" :icon="mdiWifiOff" type="warning">
          <b class="font-semibold">No connection.</b> What you type stays in this page and is saved when the connection returns. Keep this page open: closing it loses the text that is not saved yet.
        </FeedbackBanner>

        <FeedbackBanner v-if="conflict" type="info">
          <b class="font-semibold">Someone saved changes while you were editing.</b>
          Their version is on the page now. Your last change was not saved.
          <div v-for="item in conflict.lost" :key="item.label" class="mt-2 flex flex-col gap-1">
            <span class="text-xs font-medium">{{ item.label }}</span>
            <div class="whitespace-pre-wrap rounded-sm border border-current px-2 py-1">{{ item.text }}</div>
            <v-btn class="self-start" size="small" variant="outlined" @click="copy(item.text)">Copy my text</v-btn>
          </div>

          <v-btn class="mt-2" size="small" variant="text" @click="dismissConflict()">Dismiss</v-btn>
        </FeedbackBanner>

        <FeedbackBanner v-if="problem" type="error">{{ problem }}</FeedbackBanner>

        <FeedbackBanner v-if="stopped" :type="stopped.tone">
          <b class="font-semibold">{{ stopped.title }}</b> {{ stopped.text }}
        </FeedbackBanner>

        <FeedbackBanner v-if="report.status === 'finalizing'" type="info">
          <div class="flex items-center gap-2">
            <v-progress-circular indeterminate size="16" width="2" />
            <b class="font-semibold">Finalizing…</b>
          </div>

          <p class="m-0 mt-1">The boards are locked while the PDF is made. This takes up to a minute. You can leave this page.</p>
        </FeedbackBanner>

        <FeedbackBanner v-if="report.status === 'superseded'" type="info">
          <b class="font-semibold">This version was replaced.</b> It is kept as it was finalized. {{ newer ? 'The corrected version is below.' : '' }}
        </FeedbackBanner>

        <FeedbackBanner v-if="report.status === 'draft' && report.supersedes_id" type="info">
          <b class="font-semibold">This is a correction of an earlier version.</b> The earlier version is kept. This one has to be signed again.
        </FeedbackBanner>
      </div>

      <div v-if="!content" class="flex items-start gap-3 rounded-lg bg-surface-50 px-3.5 py-3 text-sm" role="status">
        <v-progress-circular
          class="mt-0.5"
          color="primary"
          indeterminate
          size="18"
          width="2"
        />

        <p class="m-0">The draft is still being made. It appears here in a moment.</p>
      </div>

      <div v-else class="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div class="flex min-w-0 flex-col gap-4">
          <section aria-labelledby="re-sum" class="flex flex-col gap-3 rounded-card border border-surface-200 bg-surface p-4">
            <h2 id="re-sum" class="m-0 text-h4 text-surface-900">Summary</h2>

            <FormField id="re-summary" label="What was done, in a few sentences">
              <v-textarea
                id="re-summary"
                auto-grow
                :counter="SUMMARY_MAX"
                :model-value="fields.summary"
                name="summary"
                :readonly="!editable"
                rows="3"
                @update:model-value="set('summary', $event)"
              />
            </FormField>
          </section>

          <section aria-labelledby="re-st" class="flex flex-col gap-4 rounded-card border border-surface-200 bg-surface p-4">
            <h2 id="re-st" class="m-0 text-h4 text-surface-900">Stations</h2>

            <div v-for="station in content.facts.stations" :key="station.station_id" class="flex flex-col gap-1">
              <div class="flex flex-wrap items-baseline gap-2">
                <strong class="font-mono text-sm" translate="no">{{ station.code }}</strong>
                <span class="text-sm text-surface-700">{{ station.name }}</span>
              </div>

              <FormField :id="`re-w-${station.station_id}`" label="Work performed">
                <v-textarea
                  :id="`re-w-${station.station_id}`"
                  auto-grow
                  :model-value="fields.stations[station.station_id] ?? ''"
                  :name="`work-${station.code}`"
                  placeholder="Nothing written yet"
                  :readonly="!editable"
                  rows="3"
                  @update:model-value="setStation(station.station_id, $event)"
                />
              </FormField>
            </div>
          </section>

          <section aria-labelledby="re-rec" class="flex flex-col gap-3 rounded-card border border-surface-200 bg-surface p-4">
            <h2 id="re-rec" class="m-0 text-h4 text-surface-900">Recommendations and follow-up</h2>

            <FormField id="re-recs" label="Recommendations">
              <v-textarea
                id="re-recs"
                auto-grow
                :model-value="fields.recommendations"
                name="recommendations"
                :readonly="!editable"
                rows="3"
                @update:model-value="set('recommendations', $event)"
              />
            </FormField>

            <FormField id="re-fu" label="Follow-up">
              <v-textarea
                id="re-fu"
                auto-grow
                :model-value="fields.follow_up"
                name="follow-up"
                :readonly="!editable"
                rows="2"
                @update:model-value="set('follow_up', $event)"
              />
            </FormField>
          </section>

          <FactsPanel :facts="facts" :visit-id="report.visit_id ?? null" />

          <PhotosPanel
            :editable="editable"
            :fields="fields"
            :groups="groups"
            :thumbs="thumbs"
            @body="(id, on) => { fields.inBody[id] = on; touch(`body:${id}`) }"
            @caption="(id, text) => { fields.captions[id] = text; touch(`caption:${id}`) }"
          />
        </div>

        <aside aria-label="Actions and signatures" class="flex min-w-0 flex-col gap-4">
          <SignaturesPanel
            :attended="attended(report, who)"
            :editable="editable"
            :people="people"
            :report="report"
            :who="who"
            :zone="zone"
            @sign="startSigning"
          />

          <section aria-labelledby="re-act" class="flex flex-col gap-3 rounded-card border border-surface-200 bg-surface p-4">
            <h2 id="re-act" class="m-0 text-h4 text-surface-900">Report</h2>

            <template v-if="report.status === 'draft'">
              <v-btn
                v-if="isLead(report, who) || who.isAdmin"
                color="primary"
                :disabled="!mayFinalize(report, who) || !online"
                @click="finalizing = true"
              >Finalize</v-btn>

              <p class="m-0 text-xs text-surface-600">Finalize is available to the lead, or an admin, once the lead has signed. It locks the visit’s boards.</p>
            </template>

            <template v-else-if="report.status === 'final'">
              <dl class="m-0 grid grid-cols-[90px_1fr] gap-x-3 gap-y-1 text-sm">
                <dt class="text-surface-600">Finalized</dt>
                <dd class="m-0">{{ finalizedAt }}<span v-if="finalizedBy"> by {{ finalizedBy }}</span></dd>
                <dt class="text-surface-600">Signed by</dt>
                <dd class="m-0">{{ signedNames }}</dd>
                <dt class="text-surface-600">Verification</dt>
                <dd class="m-0 font-mono text-xs break-all">{{ report.pdf_sha256 }}</dd>
              </dl>

              <v-btn color="primary" :disabled="!online" :prepend-icon="mdiDownloadOutline" @click="download()">Download PDF</v-btn>
              <v-btn v-if="mayReopen(report, who)" :disabled="!online" variant="outlined" @click="reopening = true">Reopen for correction</v-btn>
              <p v-if="mayReopen(report, who)" class="m-0 text-xs text-surface-600">Admins only. The report is kept as it is and a new version starts.</p>
            </template>

            <template v-else-if="report.status === 'superseded'">
              <v-btn :disabled="!online" :prepend-icon="mdiDownloadOutline" variant="outlined" @click="download()">Download this version</v-btn>
            </template>
          </section>

          <section v-if="versions.length > 1" aria-labelledby="re-ver" class="flex flex-col gap-2 rounded-card border border-surface-200 bg-surface p-4">
            <h2 id="re-ver" class="m-0 text-h4 text-surface-900">Versions</h2>

            <ul class="m-0 flex list-none flex-col p-0">
              <li v-for="v in versions" :key="v.id" class="flex flex-wrap items-center gap-2 border-t border-surface-200 py-2 first:border-t-0">
                <router-link
                  :aria-current="v.id === report.id ? 'page' : undefined"
                  class="text-sm font-medium text-primary"
                  :to="{ name: 'visit-report', params: { id: v.id } }"
                >{{ statusLabel(v) }}</router-link>

                <span v-if="v.id === report.id" class="text-xs text-surface-600">this one</span>
              </li>
            </ul>
          </section>
        </aside>
      </div>
    </div>

    <ReportPreviewDialog
      v-if="report"
      v-model="previewing"
      :fetch-link="link"
      :reason="problem"
      :report="report"
    />

    <SignDialog
      v-if="report"
      v-model="signing"
      :attestation="report.attestation ?? ''"
      :busy="busy === 'sign'"
      :failure="signFailure"
      :lead="isLead(report, who)"
      :number="report.number"
      :suggest="session.user?.name ?? ''"
      :version="report.version"
      @sign="sign"
    />

    <ConfirmDialogs
      v-if="report"
      v-model:finalizing="finalizing"
      v-model:reopening="reopening"
      :busy="busy === 'finalize' || busy === 'reopen'"
      :failure="confirmFailure"
      :signed-by="signedLine"
      :version="report.version"
      @finalize="finalize"
      @reopen="reopen"
    />
  </PageBody>
</template>

<script lang="ts" setup>
  import type { ReportSummary } from '@/api/models'
  import { mdiCheck, mdiDownloadOutline, mdiFileEyeOutline, mdiWifiOff } from '@mdi/js'
  import { storeToRefs } from 'pinia'
  import { computed, ref, watch } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { reportsApi } from '@/api/report'
  import { useOnline } from '@/app/composables/useOnline'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import FormField from '@/components/FormField.vue'
  import PageBody from '@/components/PageBody.vue'
  import { useSessionStore } from '@/stores/session'
  import { formatWhen } from '../../visits'
  import ReportPreviewDialog from '../ReportPreviewDialog.vue'
  import ConfirmDialogs from './ConfirmDialogs.vue'
  import FactsPanel from './FactsPanel.vue'
  import PhotosPanel from './PhotosPanel.vue'
  import { attended, factsOf, isLead, mayFinalize, mayReopen, photoGroups, statusLabel, stoppedWords } from './rules'
  import SignaturesPanel from './SignaturesPanel.vue'
  import SignDialog from './SignDialog.vue'
  import { useReportEditor } from './useReportEditor'
  import { useThumbs } from './useThumbs'

  // The report page of /visit-reports/:id (AFD J7, PRD RPT-2, RPT-4 to RPT-6; boards 4 to 6 of the
  // W16 sheet and the W17 sheet). Staff write the narrative and choose the photos, sign, finalize
  // and (admins) reopen. Every action needs a connection (OFF-10); nothing is kept on the device.
  const SUMMARY_MAX = 4000

  const route = useRoute()
  const router = useRouter()
  const session = useSessionStore()
  const { isAdmin } = storeToRefs(session)
  const online = useOnline()

  const id = computed(() => String(route.params.id))
  const who = computed(() => ({ id: session.user?.id ?? '', isAdmin: isAdmin.value }))

  const editor = useReportEditor(id)
  const { report, loaded, notFound, fields, content, editable, saveState, conflict, problem, busy } = editor
  const { touch, sign: signReport, finalize: finalizeReport, reopen: reopenReport, link, dismissConflict } = editor

  const backTo = computed(() => ({ name: 'visits', params: { id: report.value?.visit_id ?? undefined } }))
  const facts = computed(() => content.value ? factsOf(content.value) : [])
  const groups = computed(() => content.value ? photoGroups(content.value) : [])
  const thumbs = useThumbs(computed(() => groups.value.flatMap(g => g.photos.map(p => p.mediaId))))
  const people = computed(() => Object.fromEntries((content.value?.facts.visit.staff ?? []).map(p => [p.id, p.name])))
  const zone = computed(() => content.value?.facts.stations.find(s => s.time_zone)?.time_zone ?? null)
  const request = computed(() => {
    const visit = content.value?.facts.visit
    return visit?.request_ref ? [visit.request_ref, visit.request_title].filter(Boolean).join(' · ') : ''
  })
  const stopped = computed(() => report.value?.status === 'draft' ? stoppedWords(report.value.finalize_error) : null)
  const chip = computed(() => ({
    draft: 'border-warning bg-warning-container text-on-warning-container',
    finalizing: 'border-info bg-info-container text-on-info-container',
    final: 'border-success bg-success-container text-on-success-container',
    superseded: 'border-surface-500 bg-surface-100 text-surface-800',
  })[report.value?.status ?? 'draft'] ?? '')

  const saveWords = computed(() => {
    switch (saveState.value) {
      case 'saving': {
        return 'Saving…'
      }
      case 'retrying': {
        return 'Not saved yet. Retrying…'
      }
      case 'dirty': {
        return 'Typing…'
      }
      default: {
        return editor.savedAt.value ? `Saved ${editor.savedAt.value.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : 'Saved'
      }
    }
  })

  // The versions of this visit's report, newest first, for the list and the link to a correction
  const versions = ref<ReportSummary[]>([])
  const newer = computed(() => versions.value.some(v => report.value && v.version > report.value.version))
  watch(() => [report.value?.visit_id, report.value?.status, report.value?.version], async () => {
    const visit = report.value?.visit_id
    if (!visit) {
      return
    }
    try {
      versions.value = await reportsApi.list(`visit:${visit}`)
    } catch {
      // The list is a convenience: the page works without it
    }
  }, { immediate: true })

  function set (key: 'summary' | 'recommendations' | 'follow_up', value: string): void {
    fields[key] = value
    touch(key)
  }

  function setStation (stationId: string, value: string): void {
    fields.stations[stationId] = value
    touch(`station:${stationId}`)
  }

  async function copy (text: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      // Selecting the text by hand still works
    }
  }

  // --- the dialogs ---

  const previewing = ref(false)
  const signing = ref(false)
  const finalizing = ref(false)
  const reopening = ref(false)
  const signFailure = ref<string | null>(null)
  const confirmFailure = ref<string | null>(null)

  async function preview (): Promise<void> {
    busy.value = 'preview'
    // Save what was typed, then draw: the link function does both
    const ready = await link()
    busy.value = null
    if (ready) {
      previewing.value = true
    }
  }

  async function download (): Promise<void> {
    const found = await link()
    if (found) {
      const a = document.createElement('a')
      a.href = found.url
      a.download = found.filename
      a.rel = 'noopener'
      a.click()
    }
  }

  function startSigning (): void {
    signFailure.value = null
    signing.value = true
  }

  async function sign (name: string, image: string): Promise<void> {
    signFailure.value = null
    const outcome = await signReport(name, image)
    if (outcome.ok || outcome.kind === 'already') {
      signing.value = false
    } else {
      signFailure.value = outcome.message
      if (outcome.kind === 'changed') {
        signing.value = false
      }
    }
  }

  async function finalize (): Promise<void> {
    confirmFailure.value = null
    const outcome = await finalizeReport()
    if (outcome.ok) {
      finalizing.value = false
    } else {
      confirmFailure.value = outcome.message
    }
  }

  async function reopen (reason: string): Promise<void> {
    confirmFailure.value = null
    const { outcome, next } = await reopenReport(reason)
    if (outcome.ok && next) {
      reopening.value = false
      await router.push({ name: 'visit-report', params: { id: next.id } })
    } else if (!outcome.ok) {
      confirmFailure.value = outcome.message
    }
  }

  watch([finalizing, reopening], () => {
    confirmFailure.value = null
  })

  const finalizedAt = computed(() => report.value?.finalized_at ? formatWhen(report.value.finalized_at, zone.value ?? undefined) : '')
  const finalizedBy = computed(() => report.value?.finalized_by ? people.value[report.value.finalized_by] ?? '' : '')
  const signedNames = computed(() => (report.value?.signatures ?? []).filter(s => s.valid).map(s => `${s.typed_name}${s.signer_id === report.value?.lead_staff_id ? ' (lead)' : ''}`).join(', ') || 'No one')
  const signedLine = computed(() => {
    const lead = report.value?.signatures.find(s => s.valid && s.signer_id === report.value?.lead_staff_id)
    return lead ? `Signed by ${lead.typed_name} on ${formatWhen(lead.signed_at, zone.value ?? undefined)}.` : ''
  })
</script>
