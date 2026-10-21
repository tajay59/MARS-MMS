<template>
  <ModalSheet v-model="open" labelledby="rv-h" max-width="460" persistent>
    <form class="flex flex-col gap-4" novalidate @submit.prevent="submit">
      <h2 id="rv-h" class="m-0 text-h2 text-surface-900">Reschedule visit</h2>

      <FeedbackBanner v-if="problem" type="error">{{ problem }}</FeedbackBanner>

      <div class="grid gap-4 sm:grid-cols-2">
        <FormField id="rv-start" label="Starts">
          <v-text-field
            id="rv-start"
            v-model="start"
            autocomplete="off"
            :error-messages="errors.start"
            name="start"
            type="datetime-local"
          />
        </FormField>

        <FormField id="rv-end" label="Ends">
          <v-text-field
            id="rv-end"
            v-model="end"
            autocomplete="off"
            :error-messages="errors.end"
            name="end"
            type="datetime-local"
          />
        </FormField>
      </div>

      <p class="m-0 -mt-2 text-sm text-surface-600">Times are in {{ zoneName }} time ({{ zone }}).</p>

      <!-- Filled in when a visit can be prepared on a phone (Phase 5): who has it, so the warning names them -->
      <p v-if="preparedOn" class="m-0 rounded-lg bg-surface-50 px-3.5 py-3 text-sm text-surface-900 shadow-[inset_3px_0_0_var(--v-theme-primary)]">
        This visit is prepared on {{ preparedOn }}’s phone. Work recorded there before it syncs may come back as a conflict.
      </p>

      <p class="m-0 text-sm text-surface-600">Everyone attending and the client are told the new dates.</p>

      <div class="flex flex-wrap justify-end gap-2">
        <v-btn class="text-primary" variant="text" @click="requestClose">Keep it</v-btn>
        <v-btn color="primary" :loading="busy" type="submit">Reschedule</v-btn>
      </div>
    </form>

    <DiscardConfirm v-model="askLeave" message="Your new dates will be lost." @leave="leave" />
  </ModalSheet>
</template>

<script lang="ts" setup>
  import type { VisitOut } from '@/api/models'
  import { computed, ref, watch } from 'vue'
  import { visitsApi } from '@/api/operations'
  import { useFormDialog } from '@/app/composables/useFormDialog'
  import DiscardConfirm from '@/components/DiscardConfirm.vue'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import FormField from '@/components/FormField.vue'
  import ModalSheet from '@/components/ModalSheet.vue'
  import { failureOf } from './failures'
  import { utcToZoned, validateSchedule, visitZone, zonedToUtc, zoneLabel } from './visits'

  // Reschedule (PRD VIS-2; AFD J5 step 5): new dates for a planned visit, in the zone of its first
  // station. The people and stations stay; use Change owner for those.
  const props = defineProps<{ visit: VisitOut, preparedOn?: string }>()

  const emit = defineEmits<{ done: [visit: VisitOut], changed: [] }>()
  const open = defineModel<boolean>({ required: true })

  const zone = computed(() => visitZone(props.visit) ?? Intl.DateTimeFormat().resolvedOptions().timeZone)
  const zoneName = computed(() => zoneLabel(zone.value))
  const start = ref('')
  const end = ref('')
  const errors = ref<{ start?: string, end?: string }>({})
  const problem = ref<string | null>(null)
  const busy = ref(false)

  const original = computed(() => [utcToZoned(props.visit.planned_start, zone.value), utcToZoned(props.visit.planned_end, zone.value)])
  const { askLeave, requestClose, leave } = useFormDialog(open, () => !busy.value && (start.value !== original.value[0] || end.value !== original.value[1]))

  watch(open, isOpen => {
    if (isOpen) {
      start.value = original.value[0]!
      end.value = original.value[1]!
      errors.value = {}
      problem.value = null
    }
  }, { immediate: true })

  async function submit (): Promise<void> {
    if (busy.value) {
      return
    }
    // Only the dates are checked here: the people and stations are not on this form
    const found = validateSchedule({ start: start.value, end: end.value, staffIds: ['-'], leadId: '-', owners: { '-': '-' } }, zone.value)
    errors.value = { start: found.start, end: found.end }
    if (found.start || found.end) {
      return
    }
    busy.value = true
    problem.value = null
    try {
      const done = await visitsApi.update(props.visit.id, {
        planned_start: zonedToUtc(start.value, zone.value)!,
        planned_end: zonedToUtc(end.value, zone.value)!,
        version: props.visit.version,
      })
      open.value = false
      emit('done', done)
    } catch (error) {
      const failure = failureOf(error, 'We couldn’t reschedule. Try again in a moment.')
      if (failure.field === 'planned_end' || failure.field === 'planned_start') {
        errors.value = { [failure.field === 'planned_end' ? 'end' : 'start']: failure.message }
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
