<template>
  <form class="grid gap-6 md:grid-cols-[minmax(0,480px)_minmax(0,1fr)] md:gap-8" novalidate @submit.prevent="submit">
    <div class="flex flex-col gap-4">
      <p class="m-0 text-surface-600">The essentials first. Sensors, equipment, access notes and the install date go on the station’s page next.</p>

      <div aria-live="polite" class="flex flex-col gap-3 empty:hidden">
        <FeedbackBanner v-if="problem === 'offline'" type="warning">
          This needs a connection. What you typed is still here; save when you have signal.
        </FeedbackBanner>

        <FeedbackBanner v-else-if="problem" type="error">{{ problem }}</FeedbackBanner>
        <FeedbackBanner v-if="loadProblem" type="error">{{ loadProblem }}</FeedbackBanner>
      </div>

      <div class="grid items-start gap-4 sm:grid-cols-[160px_minmax(0,1fr)]">
        <FormField :id="fieldId('code')" label="Code">
          <v-text-field
            :id="fieldId('code')"
            v-model="values.code"
            autocomplete="off"
            class="[&_input]:font-mono"
            :error-messages="errors.code"
            name="code"
            spellcheck="false"
            @blur="values.code = values.code.trim().toUpperCase()"
          />
        </FormField>

        <FormField :id="fieldId('name')" label="Name">
          <v-text-field
            :id="fieldId('name')"
            v-model="values.name"
            autocomplete="off"
            :error-messages="errors.name"
            name="name"
          />
        </FormField>
      </div>

      <FormField :id="fieldId('ownerOrgId')" label="Owner organization">
        <v-autocomplete
          :id="fieldId('ownerOrgId')"
          v-model="values.ownerOrgId"
          :error-messages="errors.ownerOrgId"
          hint="Stations never change owner, so choose with care."
          item-title="name"
          item-value="id"
          :items="orgs"
          :loading="orgsLoading"
          name="owner_org_id"
          no-data-text="No active organizations"
          persistent-hint
        />
      </FormField>

      <div class="grid items-start gap-4 sm:grid-cols-2">
        <FormField :id="fieldId('country')" label="Country">
          <v-autocomplete
            :id="fieldId('country')"
            :error-messages="errors.country"
            :items="countryItems"
            :model-value="values.country"
            name="country"
            no-data-text="No country by that name"
            @update:model-value="setCountry"
          />
        </FormField>

        <FormField :id="fieldId('timeZone')" label="Time zone">
          <v-text-field
            v-if="zoneChoices.length <= 1"
            :id="fieldId('timeZone')"
            :error-messages="errors.timeZone"
            :hint="values.country ? (zoneChoices.length === 1 ? 'Set from the country.' : 'No zones listed for this country.') : 'Choose the country first.'"
            :model-value="values.timeZone"
            name="time_zone"
            persistent-hint
            readonly
          />

          <v-select
            v-else
            :id="fieldId('timeZone')"
            v-model="values.timeZone"
            :error-messages="errors.timeZone"
            :items="zoneChoices"
            name="time_zone"
          />
        </FormField>
      </div>

      <fieldset class="m-0 flex flex-col gap-2 border-0 p-0">
        <legend class="mb-2 p-0 font-heading text-h3 text-surface-900">Location</legend>

        <div class="grid items-start gap-4 sm:grid-cols-2">
          <FormField :id="fieldId('latitude')" label="Latitude">
            <v-text-field
              :id="fieldId('latitude')"
              v-model="values.latitude"
              autocomplete="off"
              :error-messages="errors.latitude"
              inputmode="decimal"
              name="latitude"
            />
          </FormField>

          <FormField :id="fieldId('longitude')" label="Longitude">
            <v-text-field
              :id="fieldId('longitude')"
              v-model="values.longitude"
              autocomplete="off"
              :error-messages="errors.longitude"
              inputmode="decimal"
              name="longitude"
            />
          </FormField>
        </div>

        <p class="m-0 text-sm text-surface-600">Click or tap the map to drop the pin, or type the coordinates.</p>

        <!-- Phones: the map right here, before the buttons, so the hint above points at it -->
        <div v-if="!mdAndUp" class="mt-1 h-72 overflow-hidden rounded-card">
          <PinMap
            :focus="focus"
            :latitude="pinLat"
            :longitude="pinLon"
            :others="others"
            @pick="pick"
          />
        </div>
      </fieldset>

      <div class="mt-2 flex flex-wrap justify-end gap-2 border-t border-surface-200 pt-4">
        <v-btn class="text-primary" variant="text" @click="cancel">Cancel</v-btn>
        <v-btn color="primary" :loading="busy" type="submit">Add station</v-btn>
      </div>
    </div>

    <div v-if="mdAndUp" class="sticky top-0 h-[calc(100dvh-180px)] min-h-96 overflow-hidden rounded-card">
      <PinMap
        :focus="focus"
        :latitude="pinLat"
        :longitude="pinLon"
        :others="others"
        @pick="pick"
      />
    </div>

    <DiscardConfirm v-model="askLeave" message="The new station will be lost." @leave="leave" />
  </form>
</template>

<script lang="ts" setup>
  import type { FieldErrors, FieldKey } from './stationFormModel'
  import type { StationDetail, StationSummary } from '@/api/models'
  import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
  import { useDisplay } from 'vuetify'
  import { orgsApi } from '@/api/auth'
  import { stationsApi } from '@/api/operations'
  import { ApiError, NetworkError } from '@/api/problem'
  import { useLeaveGuard } from '@/app/composables/useLeaveGuard'
  import { countries } from '@/app/countries'
  import DiscardConfirm from '@/components/DiscardConfirm.vue'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import FormField from '@/components/FormField.vue'
  import PinMap from './PinMap.vue'
  import { createBody, emptyValues, onlyZone, parseNumber, problemOf, validate } from './stationFormModel'

  // New station, the essentials (approved "AWS-MMS Stations redesign"; PRD STN-1): code, name,
  // owner, country and zone, and a place. The rest of the station is edited on its page. It needs a
  // connection (OFF-10); what is typed stays on screen when a save fails.
  const props = defineProps<{ stations: readonly StationSummary[] }>()
  const emit = defineEmits<{ saved: [station: StationDetail], cancel: [] }>()

  const { mdAndUp } = useDisplay()
  const values = reactive(emptyValues())
  const initial = JSON.stringify(values)
  const errors = ref<FieldErrors>({})
  const problem = ref<'offline' | string | null>(null)
  const loadProblem = ref<string | null>(null)
  const busy = ref(false)
  const clean = ref(false)
  const dirty = computed(() => !clean.value && JSON.stringify(values) !== initial)

  function fieldId (key: string): string {
    return `sq-${key}`
  }

  const countryItems = countries()
  const orgs = ref<{ id: string, name: string }[]>([])
  const orgsLoading = ref(true)
  const zonesByCountry = ref<Record<string, string[]>>({})
  const zoneChoices = computed(() => zonesByCountry.value[values.country] ?? [])

  function setCountry (code: string | null): void {
    values.country = code ?? ''
    const found = zonesByCountry.value[values.country] ?? []
    values.timeZone = found.length === 1 ? (found[0] ?? '') : (found.includes(values.timeZone) ? values.timeZone : '')
  }

  // --- The map ----------------------------------------------------------------------------------

  function coordinate (text: string, limit: number): number | null {
    const n = parseNumber(text)
    return n === null || Number.isNaN(n) || Math.abs(n) > limit ? null : n
  }

  const pinLat = computed(() => coordinate(values.latitude, 90))
  const pinLon = computed(() => pinLat.value === null ? null : coordinate(values.longitude, 180))
  // The chosen country's stations: the map looks there until there is a pin
  const focus = computed<[number, number][]>(() => props.stations.flatMap(s =>
    s.country === values.country && s.latitude !== null && s.longitude !== null ? [[s.latitude, s.longitude] as [number, number]] : []))
  const others = computed(() => props.stations.flatMap(s =>
    s.latitude !== null && s.longitude !== null
      ? [{ latitude: s.latitude, longitude: s.longitude, code: s.code }]
      : []))

  function pick (latitude: number, longitude: number): void {
    values.latitude = String(latitude)
    values.longitude = String(longitude)
  }

  // --- Choices ----------------------------------------------------------------------------------

  async function loadChoices (): Promise<void> {
    const [places, active] = await Promise.allSettled([stationsApi.places(), orgsApi.list('active')])
    if (places.status === 'fulfilled') {
      zonesByCountry.value = places.value.time_zones
      if (!values.timeZone && values.country) {
        values.timeZone = onlyZone(values.country, zonesByCountry.value) ?? ''
      }
    }
    if (active.status === 'fulfilled') {
      orgs.value = active.value.items.map(o => ({ id: o.id, name: o.name })).toSorted((a, b) => a.name.localeCompare(b.name))
    }
    if (places.status === 'rejected' || active.status === 'rejected') {
      const offline = [places, active].some(r => r.status === 'rejected' && r.reason instanceof NetworkError)
      loadProblem.value = offline
        ? 'This needs a connection to list the countries and organizations. It will load when you have signal.'
        : 'We couldn’t load the countries or organizations. Reload the page to try again.'
    }
    orgsLoading.value = false
  }

  onMounted(loadChoices)

  // --- Saving -----------------------------------------------------------------------------------

  // Fix a field and its message goes away
  watch(values, () => {
    if (Object.keys(errors.value).length > 0) {
      const now = validate(values, 'new')
      errors.value = Object.fromEntries(Object.entries(errors.value).filter(([key]) => key in now))
    }
  }, { deep: true })

  async function focusField (key: FieldKey): Promise<void> {
    await nextTick()
    const el = document.querySelector<HTMLElement>(`#${fieldId(key)}`)
    el?.scrollIntoView({ block: 'center' })
    el?.focus()
  }

  async function submit (): Promise<void> {
    values.code = values.code.trim().toUpperCase()
    problem.value = null
    const found = validate(values, 'new')
    errors.value = found
    const first = Object.keys(found)[0] as FieldKey | undefined
    if (first) {
      await focusField(first)
      return
    }
    busy.value = true
    try {
      const saved = await stationsApi.create(createBody(values))
      clean.value = true
      emit('saved', saved)
    } catch (error) {
      if (error instanceof NetworkError) {
        problem.value = 'offline'
      } else if (error instanceof ApiError) {
        const found = problemOf(error)
        if (found.kind === 'fields') {
          errors.value = found.errors
          problem.value = found.message
          const key = Object.keys(found.errors)[0] as FieldKey | undefined
          if (key) {
            await focusField(key)
          }
        } else {
          problem.value = found.kind === 'other' ? found.message : 'We couldn’t save the station. Try again in a moment.'
        }
      } else {
        problem.value = 'We couldn’t save the station. Try again in a moment.'
      }
    } finally {
      busy.value = false
    }
  }

  // --- Leaving with unsaved changes -------------------------------------------------------------

  const { askLeave, confirmLeave, leave } = useLeaveGuard(dirty)

  async function cancel (): Promise<void> {
    if (await confirmLeave()) {
      clean.value = true
      emit('cancel')
    }
  }

  function warnUnload (event: BeforeUnloadEvent): void {
    if (dirty.value) {
      event.preventDefault()
    }
  }

  window.addEventListener('beforeunload', warnUnload)
  onBeforeUnmount(() => window.removeEventListener('beforeunload', warnUnload))

  defineExpose({ confirmLeave, dirty })
</script>
