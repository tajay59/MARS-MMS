<template>
  <section aria-labelledby="rs-h" class="flex flex-col gap-2">
    <div class="flex items-baseline justify-between gap-3">
      <h2 id="rs-h" class="m-0 text-h3 text-surface-900">Report</h2>

      <span v-if="report" class="text-sm text-surface-600">
        <span class="font-mono" translate="no">{{ report.number }}</span> · {{ versionText(report) }} · {{ statusText(report.status) }}
      </span>
    </div>

    <!-- Right after the end: the draft is made once the visit has synced -->
    <div v-if="!report" class="flex items-start gap-3 rounded-lg bg-surface-50 px-3.5 py-3 text-sm text-surface-900" role="status">
      <v-progress-circular
        v-if="looking"
        class="mt-0.5"
        color="primary"
        indeterminate
        size="18"
        width="2"
      />

      <div class="min-w-0">
        <p class="m-0 font-medium">{{ looking ? 'Your draft is being made' : 'No draft yet' }}</p>
        <p class="m-0 text-surface-700">{{ looking ? 'It starts when the visit has synced.' : 'It is made once the visit has synced. If it does not appear, open this page again.' }}</p>
      </div>
    </div>

    <div v-else class="flex flex-col gap-3 rounded-lg bg-surface-50 px-3.5 py-3">
      <div class="flex items-start gap-3">
        <span class="mt-0.5 grid size-9 flex-none place-items-center rounded-full" :class="disc">
          <v-progress-circular v-if="words.tone === 'working'" indeterminate size="18" width="2" />
          <v-icon v-else :icon="icon" size="20" />
        </span>

        <div aria-live="polite" class="min-w-0 text-sm">
          <p class="m-0 font-medium text-surface-900">{{ words.title }}</p>
          <p class="m-0 text-surface-700">{{ words.text }}</p>
          <p v-if="report.pdf.rendered_at" class="m-0 mt-0.5 text-xs text-surface-600">Last drawn {{ drawn }}</p>
        </div>
      </div>

      <p v-if="!online" class="m-0 text-sm text-surface-700">Needs a connection. A report is read online only.</p>
      <p v-else-if="state.problem.value" class="m-0 text-sm text-error" role="alert">{{ state.problem.value }}</p>

      <div v-if="online" class="flex flex-wrap gap-2 max-md:flex-col">
        <v-btn
          :block="!mdAndUp"
          color="primary"
          :prepend-icon="mdiPencilOutline"
          :to="{ name: 'visit-report', params: { id: report.id } }"
          :variant="report.status === 'draft' && mayDraw ? 'flat' : 'outlined'"
        >{{ openWords }}</v-btn>

        <v-btn
          v-if="words.canOpen && !words.canDraw"
          :block="!mdAndUp"
          :prepend-icon="mdiFileEyeOutline"
          variant="outlined"
          @click="opened = true"
        >Preview</v-btn>

        <template v-else>
          <v-btn
            v-if="mayDraw && words.canDraw"
            :block="!mdAndUp"
            color="primary"
            :loading="state.drawing.value"
            :prepend-icon="mdiFileEyeOutline"
            @click="draw()"
          >{{ words.action }}</v-btn>

          <v-btn
            v-if="words.canOpen"
            :block="!mdAndUp"
            :prepend-icon="mdiFileOutline"
            variant="outlined"
            @click="opened = true"
          >Open the last drawing</v-btn>
        </template>
      </div>
    </div>

    <ReportPreviewDialog
      v-if="report"
      v-model="opened"
      :fetch-link="state.link"
      :reason="state.problem.value"
      :report="report"
    />
  </section>
</template>

<script lang="ts" setup>
  import { mdiAlertCircleOutline, mdiCheckCircleOutline, mdiClockAlertOutline, mdiFileEyeOutline, mdiFileOutline, mdiPencilOutline } from '@mdi/js'
  import { computed, ref, toRef, watch } from 'vue'
  import { useDisplay } from 'vuetify'
  import { useOnline } from '@/app/composables/useOnline'
  import { formatWhen } from '../visits'
  import ReportPreviewDialog from './ReportPreviewDialog.vue'
  import { useVisitReport } from './useVisitReport'
  import { look, statusText, versionText } from './words'

  // The visit's report as staff see it (W16, RPT-1, RPT-3; W17): its number and version, whether the
  // PDF is ready, Preview, and the way into the report page (/visit-reports/:id) to edit, sign,
  // finalize and reopen. A client has ClientReportSection instead, and the server would answer 404
  // to a draft anyway (rule 6).
  const props = defineProps<{
    visitId: string
    /** The visit has ended: the draft exists once the end has synced. */
    ended: boolean
    /** Attending staff and admins may draw a preview; viewers read only. */
    mayDraw: boolean
    zone?: string | null
  }>()

  const online = useOnline()
  const { mdAndUp } = useDisplay()
  const state = useVisitReport(toRef(props, 'visitId'), toRef(props, 'ended'))
  const { report } = state

  const opened = ref(false)
  // Attending staff and admins edit and sign a draft; everyone else reads
  const openWords = computed(() => report.value?.status === 'draft' && props.mayDraw ? 'Edit and sign' : 'Open the report')
  const words = computed(() => look(report.value!))
  // Within about two minutes of the end the draft may not exist yet: say it is on its way
  const looking = state.searching
  const drawn = computed(() => report.value?.pdf.rendered_at ? formatWhen(report.value.pdf.rendered_at, props.zone ?? undefined) : '')

  const disc = computed(() => ({
    working: 'bg-primary-100 dark:bg-primary-800 text-primary',
    ready: 'bg-success-container text-success',
    stale: 'bg-warning-container text-warning',
    failed: 'bg-error-container text-error',
  })[words.value.tone])

  const icon = computed(() => ({
    working: mdiClockAlertOutline,
    ready: mdiCheckCircleOutline,
    stale: mdiClockAlertOutline,
    failed: mdiAlertCircleOutline,
  })[words.value.tone])

  // Preview asks for the drawing and opens it when it is ready
  async function draw (): Promise<void> {
    if (await state.preview()) {
      opened.value = true
    }
  }

  // A drawing asked for finishes while the person waits: open it
  let wanted = false
  watch(() => state.drawing.value, (now, before) => {
    if (now) {
      wanted = true
    } else if (before && wanted) {
      wanted = false
      if (report.value?.pdf.state === 'ready') {
        opened.value = true
      }
    }
  })
</script>
