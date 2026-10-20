<template>
  <form class="flex flex-col [&_input]:scroll-mb-24 [&_textarea]:scroll-mb-24" novalidate @submit.prevent="submit">
    <div aria-live="polite" class="mb-2 flex flex-col gap-3 empty:hidden">
      <FeedbackBanner v-if="problem === 'stale'" type="warning">
        <p class="m-0">Someone saved this station while you were editing. Load their changes, then make yours again.</p>

        <v-btn
          class="mt-2"
          color="primary"
          size="small"
          variant="text"
          @click="emit('reload')"
        >Load their changes</v-btn>
      </FeedbackBanner>

      <FeedbackBanner v-else-if="problem === 'offline'" type="warning">
        This needs a connection. What you typed is still here; save when you have signal.
      </FeedbackBanner>

      <FeedbackBanner v-else-if="problem" type="error">{{ problem }}</FeedbackBanner>

      <FeedbackBanner v-if="summary.length > 1" type="error">
        <p class="m-0">Fix {{ summary.length }} things to save:</p>

        <ul class="m-0 mt-1 list-disc pl-5">
          <li v-for="item in summary" :key="item.key">
            <a class="text-inherit underline" :href="`#${fieldId(item.key)}`" @click.prevent="focusField(item.key)">{{ item.message }}</a>
          </li>
        </ul>
      </FeedbackBanner>

      <FeedbackBanner v-if="loadProblem" type="error">{{ loadProblem }}</FeedbackBanner>
    </div>

    <!-- Identity -->
    <section aria-labelledby="sf-identity" class="grid gap-x-8 gap-y-3 pb-2 pt-6 first:pt-0 md:grid-cols-[190px_minmax(0,1fr)]">
      <header>
        <h2 id="sf-identity" class="m-0 text-h3 text-surface-900">Identity</h2>
        <p class="m-0 mt-1 text-sm text-surface-600">How staff and the owner find it.</p>
      </header>

      <div class="grid items-start gap-4 pb-5 sm:grid-cols-2">
        <FormField :id="fieldId('code')" label="Code">
          <v-text-field
            :id="fieldId('code')"
            v-model="values.code"
            autocomplete="off"
            class="[&_input]:font-mono"
            :error-messages="errors.code"
            hint="2 to 32 characters. Printed on the QR label."
            name="code"
            persistent-hint
            spellcheck="false"
            @blur="values.code = values.code.trim().toUpperCase()"
          />
        </FormField>

        <FormField :id="fieldId('externalId')" label="External ID (optional)">
          <v-text-field
            :id="fieldId('externalId')"
            v-model="values.externalId"
            autocomplete="off"
            class="[&_input]:font-mono"
            :error-messages="errors.externalId"
            hint="Used to search and to match imports."
            name="external_id"
            persistent-hint
            placeholder="ID in the old system…"
            spellcheck="false"
          />
        </FormField>

        <div class="sm:col-span-2">
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
          <v-text-field
            v-if="station"
            :id="fieldId('ownerOrgId')"
            :append-inner-icon="mdiLockOutline"
            hint="A station keeps its owner."
            :model-value="station.owner_org_name ?? station.owner_org_id"
            name="owner"
            persistent-hint
            readonly
          />

          <v-autocomplete
            v-else
            :id="fieldId('ownerOrgId')"
            v-model="values.ownerOrgId"
            :error-messages="errors.ownerOrgId"
            hint="Active organizations only."
            item-title="name"
            item-value="id"
            :items="orgs"
            :loading="orgsLoading"
            name="owner_org_id"
            no-data-text="No active organizations"
            persistent-hint
          />
        </FormField>

        <FormField :id="fieldId('type')" label="Type (optional)">
          <v-combobox
            :id="fieldId('type')"
            v-model="values.type"
            autocomplete="off"
            :error-messages="errors.type"
            hide-no-data
            :items="suggestions.types"
            name="type"
          />
        </FormField>
      </div>
    </section>

    <!-- Place -->
    <section aria-labelledby="sf-place" class="grid gap-x-8 gap-y-3 border-t border-surface-200 pb-2 pt-6 md:grid-cols-[190px_minmax(0,1fr)]">
      <header>
        <h2 id="sf-place" class="m-0 text-h3 text-surface-900">Place</h2>
        <p class="m-0 mt-1 text-sm text-surface-600">Times are stored in UTC and shown in this time zone.</p>
      </header>

      <div class="grid items-start gap-4 pb-5 sm:grid-cols-2">
        <FormField :id="fieldId('country')" label="Country">
          <v-autocomplete
            :id="fieldId('country')"
            :error-messages="errors.country"
            :items="countryItems"
            :model-value="values.country"
            name="country"
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
            hint="This country has several zones: choose the station’s."
            :items="zoneChoices"
            name="time_zone"
            persistent-hint
          />
        </FormField>

        <FormField :id="fieldId('latitude')" label="Latitude">
          <v-text-field
            :id="fieldId('latitude')"
            v-model="values.latitude"
            autocomplete="off"
            class="[&_input]:tabular-nums"
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
            class="[&_input]:tabular-nums"
            :error-messages="errors.longitude"
            inputmode="decimal"
            name="longitude"
          />
        </FormField>

        <FormField :id="fieldId('elevation')" label="Elevation, m (optional)">
          <v-text-field
            :id="fieldId('elevation')"
            v-model="values.elevation"
            autocomplete="off"
            class="[&_input]:tabular-nums"
            :error-messages="errors.elevation"
            inputmode="decimal"
            name="elevation_m"
          />
        </FormField>

        <FormField :id="fieldId('region')" label="Region (optional)">
          <v-text-field
            :id="fieldId('region')"
            v-model="values.region"
            autocomplete="off"
            :error-messages="errors.region"
            name="region"
          />
        </FormField>

        <!-- Preview only: the Map page draws the real map -->
        <div class="flex flex-col gap-2 sm:col-span-2">
          <div
            :aria-label="point ? `Location ${point.label}` : 'No location yet'"
            class="relative grid h-32 place-items-center rounded-card bg-surface-50"
            role="img"
          >
            <v-icon v-if="point" class="text-station-operational" :icon="mdiMapMarker" size="34" />
            <span v-else class="text-sm text-surface-600">Enter the latitude and longitude to see the place.</span>
            <span v-if="point" class="absolute bottom-2 left-2.5 rounded-md bg-surface px-2 py-0.5 text-xs tabular-nums text-surface-700">{{ point.label }}</span>
          </div>

          <p class="m-0 text-sm text-surface-600">Preview only. The Map page draws the real map.</p>
        </div>

        <div class="sm:col-span-2">
          <FormField :id="fieldId('accessNotes')" label="Access notes (optional)">
            <v-textarea
              :id="fieldId('accessNotes')"
              v-model="values.accessNotes"
              auto-grow
              :error-messages="errors.accessNotes"
              hint="Staff only. Clients don’t see this."
              name="access_notes"
              persistent-hint
              rows="3"
            />
          </FormField>
        </div>
      </div>
    </section>

    <!-- Measures -->
    <section aria-labelledby="sf-measures" class="grid gap-x-8 gap-y-3 border-t border-surface-200 pb-2 pt-6 md:grid-cols-[190px_minmax(0,1fr)]">
      <header>
        <h2 id="sf-measures" class="m-0 text-h3 text-surface-900">Measures</h2>
        <p class="m-0 mt-1 text-sm text-surface-600">What the station reports. Units are installed against these later.</p>
      </header>

      <div class="flex flex-col gap-4 pb-5">
        <div class="flex flex-col gap-2">
          <span id="sf-chosen-label" class="text-label text-surface-900">Parameters</span>

          <ul v-if="values.parameters.length > 0" aria-labelledby="sf-chosen-label" class="m-0 flex list-none flex-wrap gap-1.5 p-0">
            <li v-for="code in values.parameters" :key="code">
              <v-chip closable :close-label="`Remove ${code}`" size="small" @click:close="removeParameter(code)">
                <span class="[&_input]:font-mono" translate="no">{{ code }}</span>
              </v-chip>
            </li>
          </ul>

          <p v-else class="m-0 text-sm text-surface-600">None yet.</p>
        </div>

        <FormField :id="fieldId('parameters')" label="Add a parameter">
          <v-text-field
            :id="fieldId('parameters')"
            v-model="parameterText"
            autocomplete="off"
            class="[&_input]:font-mono"
            :error-messages="errors.parameters"
            hint="Press Enter to add. Codes are capitals, numbers and _, such as AT or SOIL_T."
            name="parameter"
            persistent-hint
            spellcheck="false"
            @blur="addTyped"
            @keydown.enter.prevent="addTyped"
          />
        </FormField>

        <div v-if="suggested.length > 0" aria-label="Common parameters" class="flex flex-wrap gap-1.5" role="group">
          <button
            v-for="code in suggested"
            :key="code"
            class="inline-flex h-7 items-center rounded-full border border-dashed border-surface-500 px-2.5 font-mono text-sm text-surface-700 hover:bg-surface-100"
            translate="no"
            type="button"
            @click="addParameter(code)"
          >+ {{ code }}</button>
        </div>

        <span class="text-sm tabular-nums text-surface-600">{{ values.parameters.length }} of {{ MAX_PARAMETERS }}</span>
      </div>
    </section>

    <!-- Equipment -->
    <section aria-labelledby="sf-equipment" class="grid gap-x-8 gap-y-3 border-t border-surface-200 pb-2 pt-6 md:grid-cols-[190px_minmax(0,1fr)]">
      <header>
        <h2 id="sf-equipment" class="m-0 text-h3 text-surface-900">Equipment</h2>
        <p class="m-0 mt-1 text-sm text-surface-600">All optional. Fill in what you know.</p>
      </header>

      <div class="grid items-start gap-4 pb-5 sm:grid-cols-2">
        <FormField v-for="field in equipment" :id="fieldId(field.key)" :key="field.key" :label="field.label">
          <v-text-field
            :id="fieldId(field.key)"
            v-model="values[field.key]"
            autocomplete="off"
            :class="field.mono ? '[&_input]:font-mono' : (field.number ? '[&_input]:tabular-nums' : '')"
            :error-messages="errors[field.key]"
            :inputmode="field.number ? 'decimal' : undefined"
            :name="field.key"
            :spellcheck="field.mono ? false : undefined"
          />
        </FormField>
      </div>
    </section>

    <!-- Status -->
    <section aria-labelledby="sf-status" class="grid gap-x-8 gap-y-3 border-t border-surface-200 pb-2 pt-6 md:grid-cols-[190px_minmax(0,1fr)]">
      <header>
        <h2 id="sf-status" class="m-0 text-h3 text-surface-900">Status</h2>
      </header>

      <div class="grid items-start gap-4 pb-5 sm:grid-cols-2">
        <FormField :id="fieldId('status')" label="Status">
          <v-select
            :id="fieldId('status')"
            v-model="values.status"
            :error-messages="errors.status"
            hint="Visits and calibrations change this later."
            :items="statusItems"
            name="status"
            persistent-hint
          />
        </FormField>

        <FormField :id="fieldId('installDate')" label="Install date (optional)">
          <v-text-field
            :id="fieldId('installDate')"
            v-model="values.installDate"
            autocomplete="off"
            :error-messages="errors.installDate"
            hint="The date at the station, local time."
            name="install_date"
            persistent-hint
            type="date"
          />
        </FormField>
      </div>
    </section>

    <!-- The action bar stays in view while the form scrolls. On phones the tab bar floats a little
         above the screen's edge: the bar's own colour fills that gap so nothing shows through. -->
    <div class="sticky bottom-0 z-10 -mx-4 -mb-4 mt-2 flex flex-wrap items-center justify-between gap-3 border-t border-surface-200 bg-surface px-4 py-3 after:absolute after:inset-x-0 after:top-full after:h-12 after:bg-surface md:-mx-8 md:-mb-7 md:px-8 md:after:hidden">
      <p class="m-0 hidden text-sm text-surface-600 md:block">{{ station ? 'Saving updates the station for everyone.' : 'Saving adds the station and its QR label.' }}</p>

      <div class="flex grow gap-2 md:grow-0">
        <v-btn class="grow md:grow-0" variant="outlined" @click="cancel">Cancel</v-btn>
        <v-btn class="grow md:grow-0" color="primary" :loading="busy" type="submit">{{ station ? 'Save changes' : 'Create station' }}</v-btn>
      </div>
    </div>

    <DiscardConfirm v-model="askLeave" message="Your changes to this station will be lost." @leave="leave" />
  </form>
</template>

<script lang="ts" setup>
  import type { FieldErrors, FieldKey } from './stationFormModel'
  import type { StationDetail } from '@/api/models'
  import { mdiLockOutline, mdiMapMarker } from '@mdi/js'
  import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
  import { orgsApi } from '@/api/auth'
  import { stationsApi } from '@/api/operations'
  import { ApiError, NetworkError } from '@/api/problem'
  import { useLeaveGuard } from '@/app/composables/useLeaveGuard'
  import { countries } from '@/app/countries'
  import DiscardConfirm from '@/components/DiscardConfirm.vue'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import FormField from '@/components/FormField.vue'
  import {
    createBody,
    emptyValues,
    isUnchanged,
    MAX_PARAMETERS,
    normalizeParameter,
    onlyZone,
    parseNumber,
    patchBody,
    problemOf,
    validate,
    valuesOf,
  } from './stationFormModel'
  import { sortParameters, STATUSES, statusLook } from './stations'

  // New station and Edit station (PRD STN-1, STN-2): one form for both. It needs a connection
  // (OFF-10); what is typed stays on screen when a save fails. The server owns the rules.
  const props = defineProps<{
    /** The station being edited; absent for a new one. */
    station?: StationDetail | null
    /** Types and parameters other stations use, offered as suggestions. */
    suggestions: { types: string[], parameters: string[] }
  }>()

  const emit = defineEmits<{
    saved: [station: StationDetail]
    cancel: []
    reload: []
  }>()

  const values = reactive(props.station ? valuesOf(props.station) : emptyValues())
  const initial = JSON.stringify(values)
  const errors = ref<FieldErrors>({})
  const problem = ref<'stale' | 'offline' | string | null>(null)
  const loadProblem = ref<string | null>(null)
  const busy = ref(false)
  const parameterText = ref('')
  const clean = ref(false)

  const mode = computed(() => props.station ? 'edit' : 'new')
  const dirty = computed(() => !clean.value && JSON.stringify(values) !== initial)

  function fieldId (key: string): string {
    return `sf-${key}`
  }

  // --- Choices ----------------------------------------------------------------------------------

  const countryItems = countries()
  const statusItems = STATUSES.map(value => ({ value, title: statusLook[value].label }))
  const orgs = ref<{ id: string, name: string }[]>([])
  const orgsLoading = ref(false)
  const zonesByCountry = ref<Record<string, string[]>>({})

  interface EquipmentField { key: Exclude<FieldKey, 'parameters' | 'status'>, label: string, mono?: boolean, number?: boolean }

  const equipment: readonly EquipmentField[] = [
    { key: 'loggerModel', label: 'Logger model (optional)' },
    { key: 'loggerSerial', label: 'Logger serial (optional)', mono: true },
    { key: 'loggerFirmware', label: 'Firmware (optional)', mono: true },
    { key: 'commsType', label: 'Link type (optional)' },
    { key: 'commsProvider', label: 'Provider (optional)' },
    { key: 'commsIdentifier', label: 'SIM, IMEI or address (optional)', mono: true },
    { key: 'panelW', label: 'Solar panel, W (optional)', number: true },
    { key: 'batteryAh', label: 'Battery, Ah (optional)', number: true },
    { key: 'controller', label: 'Charge controller (optional)' },
  ]

  /** The country's zones, plus the station’s own when the list doesn't have it (an imported one). */
  const zoneChoices = computed(() => {
    const found = zonesByCountry.value[values.country] ?? []
    return values.timeZone && !found.includes(values.timeZone) && found.length > 0 ? [...found, values.timeZone] : found
  })

  function setCountry (code: string | null): void {
    values.country = code ?? ''
    const found = zonesByCountry.value[values.country] ?? []
    if (found.length === 1) {
      values.timeZone = found[0] ?? ''
    } else if (!found.includes(values.timeZone)) {
      values.timeZone = ''
    }
  }

  const point = computed(() => {
    const lat = parseNumber(values.latitude)
    const lon = parseNumber(values.longitude)
    if (lat === null || lon === null || Number.isNaN(lat) || Number.isNaN(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) {
      return null
    }
    return { label: `${lat.toFixed(4)}, ${lon.toFixed(4)}` }
  })

  async function loadChoices (): Promise<void> {
    orgsLoading.value = !props.station
    const [places, active] = await Promise.allSettled([
      stationsApi.places(),
      props.station ? Promise.resolve(null) : orgsApi.list('active'),
    ])
    if (places.status === 'fulfilled') {
      zonesByCountry.value = places.value.time_zones
      // A new station in a one-zone country that was picked before the list arrived
      if (!values.timeZone && values.country) {
        values.timeZone = onlyZone(values.country, zonesByCountry.value) ?? ''
      }
    }
    if (active.status === 'fulfilled' && active.value) {
      // A fresh array from map(): sorting it in place is safe, and toSorted needs iOS 16.
      // eslint-disable-next-line unicorn/no-array-sort
      orgs.value = active.value.items.map(o => ({ id: o.id, name: o.name })).sort((a, b) => a.name.localeCompare(b.name))
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

  // --- Parameters -------------------------------------------------------------------------------

  const suggested = computed(() => {
    const have = new Set(values.parameters)
    return sortParameters(props.suggestions.parameters).filter(p => !have.has(p)).slice(0, 7)
  })

  function addParameter (raw: string): void {
    const code = normalizeParameter(raw)
    if (code && !values.parameters.includes(code)) {
      values.parameters.push(code)
    }
  }

  function addTyped (): void {
    // Commas and spaces separate codes, so a pasted list works
    for (const part of parameterText.value.split(/[\s,;]+/)) {
      addParameter(part)
    }
    parameterText.value = ''
  }

  function removeParameter (code: string): void {
    values.parameters.splice(values.parameters.indexOf(code), 1)
  }

  // --- Saving -----------------------------------------------------------------------------------

  const hadLocation = props.station?.latitude !== null && props.station?.latitude !== undefined

  const summary = computed(() => (Object.entries(errors.value) as [FieldKey, string][])
    .filter(([, message]) => message)
    .map(([key, message]) => ({ key, message })))

  // Fix a field and its message goes away
  watch(values, () => {
    if (Object.keys(errors.value).length > 0) {
      const now = validate(values, mode.value, hadLocation)
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
    addTyped()
    values.code = values.code.trim().toUpperCase()
    problem.value = null
    const found = validate(values, mode.value, hadLocation)
    errors.value = found
    const first = Object.keys(found)[0] as FieldKey | undefined
    if (first) {
      await focusField(first)
      return
    }
    if (props.station && isUnchanged(values, props.station)) {
      emit('cancel')
      return
    }
    busy.value = true
    try {
      const saved = props.station
        ? await stationsApi.update(props.station.id, { ...patchBody(values, props.station), version: props.station.version })
        : await stationsApi.create(createBody(values))
      clean.value = true
      emit('saved', saved)
    } catch (error) {
      if (error instanceof NetworkError) {
        problem.value = 'offline'
      } else if (error instanceof ApiError) {
        const found = problemOf(error)
        if (found.kind === 'stale') {
          problem.value = 'stale'
        } else if (found.kind === 'fields') {
          errors.value = found.errors
          problem.value = found.message
          const key = Object.keys(found.errors)[0] as FieldKey | undefined
          if (key) {
            await focusField(key)
          }
        } else {
          problem.value = found.message
        }
      } else {
        problem.value = 'We couldn’t save the station. Try again in a moment.'
      }
    } finally {
      busy.value = false
    }
  }

  // --- Leaving with unsaved changes -------------------------------------------------------------

  /** The page asks before a route change; resolves true when leaving is fine. */
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
