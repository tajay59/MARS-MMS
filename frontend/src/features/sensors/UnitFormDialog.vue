<template>
  <ModalSheet
    labelledby="uf-h"
    :max-width="520"
    :model-value="open"
    persistent
    @update:model-value="onToggle"
  >
    <form class="flex flex-col gap-4" novalidate @submit.prevent="save">
      <div>
        <h2 id="uf-h" class="m-0 text-h2 text-surface-900">{{ unit ? 'Edit unit' : 'Add a unit' }}</h2>

        <p class="m-0 mt-0.5 text-sm text-surface-600">
          {{ model.manufacturer }} {{ model.model }}<template v-if="unit"> · <span class="font-mono" translate="no">{{ unit.serial }}</span></template>
        </p>
      </div>

      <FeedbackBanner v-if="stale" type="warning">
        <div class="font-semibold">Someone else changed this unit.</div>
        <div>Reload to see their changes, then make yours again.</div>
      </FeedbackBanner>

      <FeedbackBanner v-else-if="message" type="error">{{ message }}</FeedbackBanner>

      <FeedbackBanner v-if="!online" :icon="mdiWifiOff" type="warning">
        This needs a connection. What you’ve typed stays here until you’re back online.
      </FeedbackBanner>

      <FeedbackBanner v-if="installed" type="info">
        Installed at <strong class="font-semibold">{{ unit?.station?.code }}</strong><template v-if="unit?.station"> ({{ unit.station.name }})</template>.
        Remove it from the station to put it in stock or in repair.
      </FeedbackBanner>

      <FormField id="uf-serial" label="Serial number">
        <v-text-field
          id="uf-serial"
          v-model="values.serial"
          autocomplete="off"
          class="[&_input]:font-mono"
          :error-messages="errors.serial"
          maxlength="80"
          name="serial"
          spellcheck="false"
        />
      </FormField>

      <div v-if="!installed || !unit" class="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <FormField v-if="!installed" id="uf-status" label="Status">
          <v-select
            id="uf-status"
            v-model="values.status"
            :error-messages="errors.status"
            item-title="label"
            item-value="value"
            :items="unitStatusOptions"
            name="status"
          />
        </FormField>

        <FormField v-if="!unit" id="uf-calibrated" label="Last calibrated (optional)">
          <v-text-field
            id="uf-calibrated"
            v-model="values.lastCalibrated"
            :error-messages="errors.lastCalibrated"
            :max="today"
            name="last_calibrated"
            type="date"
          />
        </FormField>
      </div>

      <p v-if="!unit" class="m-0 -mt-2 text-xs text-surface-600">From the paper record. Later calibrations are recorded on the station.</p>

      <FormField id="uf-interval" label="Calibrate every (days, optional)">
        <v-text-field
          id="uf-interval"
          v-model="values.interval"
          autocomplete="off"
          :error-messages="errors.interval"
          :hint="intervalHint"
          inputmode="numeric"
          name="interval"
          persistent-hint
          :placeholder="defaultInterval ? `Model default: ${defaultInterval}` : 'No interval set'"
          suffix="days"
        />
      </FormField>

      <FormField id="uf-notes" label="Notes (optional)">
        <v-textarea
          id="uf-notes"
          v-model="values.notes"
          auto-grow
          autocomplete="off"
          :error-messages="errors.notes"
          maxlength="2000"
          name="notes"
          rows="3"
        />
      </FormField>

      <div class="mt-1 flex justify-end gap-2">
        <v-btn class="text-primary" variant="text" @click="requestClose">Cancel</v-btn>

        <v-btn v-if="stale" color="primary" variant="outlined" @click="reload">Reload</v-btn>

        <v-btn
          v-else
          color="primary"
          :disabled="!online || (unit !== null && !dirty)"
          :loading="busy"
          type="submit"
        >{{ unit ? 'Save' : 'Add unit' }}</v-btn>
      </div>
    </form>
  </ModalSheet>

  <DiscardConfirm v-model="askLeave" message="What you typed about this unit will be lost." @leave="leave" />
</template>

<script lang="ts" setup>
  import type { UnitField, UnitValues } from './sensorForms'
  import type { SensorModelOut, SensorUnitOut } from '@/api/models'
  import { mdiWifiOff } from '@mdi/js'
  import { computed, reactive, ref, watch } from 'vue'
  import { sensorUnitsApi } from '@/api/operations'
  import { ApiError, NetworkError } from '@/api/problem'
  import { focusFirstError } from '@/app/composables/focusFirstError'
  import { useFormDialog } from '@/app/composables/useFormDialog'
  import { useOnline } from '@/app/composables/useOnline'
  import DiscardConfirm from '@/components/DiscardConfirm.vue'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import FormField from '@/components/FormField.vue'
  import ModalSheet from '@/components/ModalSheet.vue'
  import { emptyUnit, localToday, unitCreateBody, unitPatchBody, unitProblem, unitStatusOptions, unitValues, validateUnit } from './sensorForms'

  // Add or edit a unit of a sensor model (PRD SEN-2, CAL-3; approved mock-up "W6 forms"). A unit
  // that is installed keeps its status here: it leaves a station only through "Remove" there.
  // Online only: nothing here is queued for sync (OFF-10).
  const props = defineProps<{
    model: SensorModelOut
    /** The unit being edited; null to add one. */
    unit: SensorUnitOut | null
  }>()

  const emit = defineEmits<{
    saved: [unit: SensorUnitOut]
    reload: []
  }>()

  const open = defineModel<boolean>({ required: true })

  const values = reactive<UnitValues>(emptyUnit())
  const errors = ref<Partial<Record<UnitField, string>>>({})
  const message = ref<string | null>(null)
  const stale = ref(false)
  const busy = ref(false)
  const today = ref(localToday())
  const initial = ref(JSON.stringify(values))

  const dirty = computed(() => JSON.stringify(values) !== initial.value)
  const installed = computed(() => props.unit?.status === 'installed')
  const defaultInterval = computed(() => props.model.default_calibration_interval_days)
  const intervalHint = computed(() => defaultInterval.value
    ? `Leave blank to use the model’s ${defaultInterval.value} days.`
    : 'Leave blank for no fixed interval.')
  const { askLeave, requestClose, leave } = useFormDialog(open, () => dirty.value)
  const online = useOnline()

  watch(open, isOpen => {
    if (!isOpen) {
      return
    }
    Object.assign(values, props.unit ? unitValues(props.unit) : emptyUnit())
    initial.value = JSON.stringify(values)
    errors.value = {}
    message.value = null
    stale.value = false
    today.value = localToday()
  }, { immediate: true })

  function onToggle (isOpen: boolean): void {
    if (!isOpen) {
      requestClose()
    }
  }

  function reload (): void {
    emit('reload')
    open.value = false
  }

  async function save (): Promise<void> {
    message.value = null
    errors.value = validateUnit(values, props.unit === null, today.value)
    if (Object.keys(errors.value).length > 0) {
      await focusFirstError()
      return
    }
    const patch = props.unit ? unitPatchBody(values, props.unit) : null
    if (props.unit && !patch) {
      open.value = false
      return
    }
    busy.value = true
    try {
      const saved = props.unit && patch
        ? await sensorUnitsApi.update(props.unit.id, patch)
        : await sensorUnitsApi.create(unitCreateBody(values, props.model.id))
      emit('saved', saved)
      open.value = false
    } catch (error) {
      if (error instanceof NetworkError) {
        message.value = 'We couldn’t reach the server. What you typed is still here: try again when you have signal.'
      } else if (error instanceof ApiError) {
        const problem = unitProblem(error, values)
        if (problem.kind === 'stale') {
          stale.value = true
        } else if (problem.kind === 'fields') {
          errors.value = problem.errors
          message.value = problem.message
          await focusFirstError()
        } else {
          message.value = problem.message
        }
      } else {
        message.value = 'We couldn’t save the unit. Try again in a moment.'
      }
    } finally {
      busy.value = false
    }
  }
</script>
