<template>
  <ModalSheet v-model="open" labelledby="ev-h" max-width="460" persistent>
    <form class="flex flex-col gap-4" novalidate @submit.prevent="submit">
      <h2 id="ev-h" class="m-0 text-h2 text-surface-900">End visit</h2>

      <FeedbackBanner v-if="problem" type="error">{{ problem }}</FeedbackBanner>

      <!-- Incomplete tasks are a warning, never a refusal (W11-33) -->
      <template v-if="incomplete.length > 0">
        <FeedbackBanner type="warning">
          <b class="font-semibold">{{ incomplete.length }} {{ incomplete.length === 1 ? 'task is' : 'tasks are' }} not complete.</b>
          You can still finish them after the visit ends, until the report is finalized.
        </FeedbackBanner>

        <ul aria-label="Tasks not complete" class="m-0 flex list-none flex-col gap-1.5 p-0">
          <li v-for="task in incomplete" :key="task.id" class="flex items-center gap-2 rounded-lg border-l-4 border-on-sticky-task bg-surface-50 px-3 py-2 text-sm">
            <span class="min-w-0 flex-1"><b class="font-semibold text-surface-900">{{ task.title }}</b><span class="text-surface-600"> · {{ task.station }}</span></span>
            <span class="flex-none text-xs font-semibold tabular-nums text-on-sticky-task">{{ task.done }} of {{ task.total }}</span>
          </li>
        </ul>
      </template>

      <fieldset class="m-0 flex min-w-0 flex-col gap-2 border-0 p-0">
        <legend class="mb-2 p-0 text-label text-surface-900">Is another visit needed?</legend>

        <v-btn-toggle
          v-model="another"
          class="self-start"
          color="primary"
          density="comfortable"
          divided
          mandatory
          variant="outlined"
        >
          <v-btn :value="true">Yes</v-btn>
          <v-btn :value="false">No</v-btn>
        </v-btn-toggle>
      </fieldset>

      <FormField v-if="another" id="ev-notes" label="What work remains">
        <v-textarea
          id="ev-notes"
          v-model="notes"
          auto-grow
          counter="2000"
          :error-messages="error"
          name="follow_up_notes"
          placeholder="For example, replace the solar panel and repaint the mast"
          rows="3"
        />
      </FormField>

      <p class="m-0 text-sm text-surface-600">
        {{ another
          ? 'The request goes back to Assigned so another visit can be scheduled. The client sees what remains.'
          : 'The visit is over. The request stays In progress until the visit report is done.' }}
      </p>

      <div class="flex flex-wrap justify-end gap-2">
        <v-btn class="text-primary" variant="text" @click="requestClose">Keep it</v-btn>
        <v-btn color="primary" :loading="busy" type="submit">{{ incomplete.length > 0 ? 'End anyway' : 'End visit' }}</v-btn>
      </div>
    </form>

    <DiscardConfirm v-model="askLeave" message="What you typed will be lost." @leave="leave" />
  </ModalSheet>
</template>

<script lang="ts" setup>
  import type { VisitOut } from '@/api/models'
  import { ref, watch } from 'vue'
  import { boardApi, visitsApi } from '@/api/operations'
  import { useFormDialog } from '@/app/composables/useFormDialog'
  import DiscardConfirm from '@/components/DiscardConfirm.vue'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import FormField from '@/components/FormField.vue'
  import ModalSheet from '@/components/ModalSheet.vue'
  import { progress } from './board'
  import { failureOf } from './failures'

  // End visit (PRD VIS-9): is another visit needed, and if so what remains. VIS-6 was dropped with
  // the visit board (W11-34). Tasks not yet complete are listed as a warning (W11-33): the server
  // never refuses an end for them, because an end synced from a phone cannot answer a question.
  const props = defineProps<{ visit: Pick<VisitOut, 'id' | 'ref' | 'stations'> }>()

  const emit = defineEmits<{ done: [visit: VisitOut], changed: [] }>()
  const open = defineModel<boolean>({ required: true })

  const another = ref(false)
  const notes = ref('')
  const error = ref<string | null>(null)
  const problem = ref<string | null>(null)
  const busy = ref(false)
  const incomplete = ref<{ id: string, title: string, station: string, done: number, total: number }[]>([])

  /** The tasks not yet complete on every station's board; a board that fails to load is skipped. */
  async function lookForIncomplete (): Promise<void> {
    incomplete.value = []
    const found = await Promise.all(props.visit.stations.map(async station => {
      try {
        const page = await boardApi.list(props.visit.id, station.station_id)
        return page.items
          .filter(e => e.kind === 'task' && !e.complete)
          .map(e => ({ id: e.id, title: e.title, station: station.station_name ?? '', ...progress(e.items) }))
      } catch {
        return []
      }
    }))
    if (open.value) {
      incomplete.value = found.flat()
    }
  }

  const { askLeave, requestClose, leave } = useFormDialog(open, () => notes.value.trim() !== '' && !busy.value)

  watch(open, isOpen => {
    if (isOpen) {
      another.value = false
      notes.value = ''
      error.value = null
      problem.value = null
      void lookForIncomplete()
    }
  }, { immediate: true })

  async function submit (): Promise<void> {
    if (busy.value) {
      return
    }
    error.value = null
    problem.value = null
    const text = notes.value.trim()
    if (another.value && !text) {
      error.value = 'Say what work remains'
      return
    }
    busy.value = true
    try {
      const done = await visitsApi.end(props.visit.id, {
        additional_visit_required: another.value,
        follow_up_notes: another.value ? text : null,
      })
      open.value = false
      emit('done', done)
    } catch (error_) {
      const failure = failureOf(error_, 'We couldn’t end the visit. Try again in a moment.')
      if (failure.field === 'follow_up_notes') {
        error.value = failure.message
      } else {
        problem.value = failure.message
      }
      if (failure.reload) {
        emit('changed')
      }
    } finally {
      busy.value = false
    }
  }
</script>
