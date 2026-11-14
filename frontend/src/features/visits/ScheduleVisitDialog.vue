<template>
  <ModalSheet v-model="open" labelledby="sv-h" max-width="600" persistent>
    <form class="flex flex-col gap-4" novalidate @submit.prevent="submit">
      <div class="flex items-start justify-between gap-3">
        <div class="min-w-0">
          <h2 id="sv-h" class="m-0 text-h2 text-surface-900">Schedule visit</h2>
          <p class="m-0 mt-0.5 font-mono text-xs font-medium text-surface-600" translate="no">{{ request.ref }}</p>
        </div>

        <v-btn
          aria-label="Close"
          icon
          size="36"
          variant="text"
          @click="requestClose"
        >
          <v-icon :icon="mdiClose" />
        </v-btn>
      </div>

      <FeedbackBanner v-if="problem" type="error">{{ problem }}</FeedbackBanner>

      <div class="grid gap-4 sm:grid-cols-2">
        <FormField id="sv-start" label="Starts">
          <v-text-field
            id="sv-start"
            v-model="values.start"
            autocomplete="off"
            :error-messages="errors.start"
            name="start"
            type="datetime-local"
          />
        </FormField>

        <FormField id="sv-end" label="Ends">
          <v-text-field
            id="sv-end"
            v-model="values.end"
            autocomplete="off"
            :error-messages="errors.end"
            name="end"
            type="datetime-local"
          />
        </FormField>
      </div>

      <p class="m-0 -mt-2 text-sm text-surface-600">
        Times are in {{ zoneName }} time ({{ zone }}). Each station shows its own local time on the visit.
      </p>

      <!-- Attending: the star marks the lead -->
      <fieldset class="m-0 flex min-w-0 flex-col gap-2 border-0 p-0">
        <legend class="mb-2 p-0 text-label text-surface-900">Attending</legend>

        <ul aria-label="Attending" class="m-0 flex list-none flex-wrap gap-2 p-0">
          <li v-for="person in attending" :key="person.id" class="inline-flex h-8 items-center rounded-full bg-primary-100 text-primary-800 dark:bg-primary-800 dark:text-primary-100">
            <button
              :aria-label="values.leadId === person.id ? `${person.name} is the lead` : `Make ${person.name} the lead`"
              :aria-pressed="values.leadId === person.id"
              class="inline-flex h-8 items-center gap-1.5 rounded-l-full pl-3 pr-1.5 text-sm font-medium"
              type="button"
              @click="values.leadId = person.id"
            >
              {{ person.name }}
              <v-icon :icon="values.leadId === person.id ? mdiStar : mdiStarOutline" size="16" />
            </button>

            <button
              :aria-label="`Remove ${person.name}`"
              class="inline-grid size-8 place-items-center rounded-r-full"
              type="button"
              @click="remove(person.id)"
            >
              <v-icon :icon="mdiClose" size="16" />
            </button>
          </li>

          <li>
            <v-menu v-model="addOpen" :close-on-content-click="false" location="bottom start">
              <template #activator="{ props: activator }">
                <button
                  v-bind="activator"
                  class="inline-flex h-8 items-center gap-1.5 rounded-full border border-surface-300 px-3 text-sm font-medium text-primary"
                  :disabled="loadingStaff || remaining.length === 0"
                  type="button"
                >
                  <v-icon :icon="mdiPlus" size="16" />Add person
                </button>
              </template>

              <div aria-label="Staff" class="flex max-h-72 min-w-56 flex-col overflow-y-auto rounded-card bg-surface py-1 shadow-lg" role="menu">
                <button
                  v-for="person in remaining"
                  :key="person.id"
                  class="flex min-h-12 flex-col items-start justify-center px-4 py-1.5 text-left hover:bg-surface-100 focus-visible:bg-surface-100"
                  role="menuitem"
                  type="button"
                  @click="add(person.id)"
                >
                  <span class="font-medium text-surface-900">{{ person.name }}</span>
                  <span class="text-sm text-surface-600">{{ roleLabel(person.roles) }}</span>
                </button>
              </div>
            </v-menu>
          </li>
        </ul>

        <p v-if="errors.staff" class="m-0 text-sm text-error" role="alert">{{ errors.staff }}</p>
        <p v-else class="m-0 text-sm text-surface-600">The star marks the lead. Tap a name to make them the lead.</p>
      </fieldset>

      <!-- Stations: the ones this visit goes to, each with one owner from those attending -->
      <fieldset class="m-0 flex min-w-0 flex-col gap-1 border-0 p-0">
        <legend class="mb-2 p-0 text-label text-surface-900">Stations and who owns each</legend>

        <div v-for="station in request.stations" :key="station.id" class="grid grid-cols-[auto_minmax(0,1fr)] items-center gap-x-3 gap-y-1 py-1.5 sm:grid-cols-[auto_minmax(0,1fr)_minmax(0,1fr)]">
          <v-checkbox-btn
            :id="`sv-st-${station.id}`"
            :aria-label="`Include ${station.name}`"
            density="comfortable"
            :disabled="Boolean(taken[station.id])"
            :model-value="station.id in values.owners"
            @update:model-value="toggleStation(station.id, Boolean($event))"
          />

          <label class="flex min-w-0 cursor-pointer flex-col" :for="`sv-st-${station.id}`">
            <span class="truncate font-medium text-surface-900">{{ station.name }}</span>
            <span class="font-mono text-xs text-surface-600" translate="no">{{ station.code }}<template v-if="taken[station.id]"> · already in {{ taken[station.id] }}</template></span>
          </label>

          <v-select
            v-if="station.id in values.owners"
            :aria-label="`Owner of ${station.name}`"
            class="col-span-2 sm:col-span-1"
            density="comfortable"
            hide-details
            item-title="label"
            item-value="id"
            :items="ownerItems"
            :model-value="values.owners[station.id]"
            @update:model-value="values.owners[station.id] = $event as string"
          />
        </div>

        <p v-if="errors.stations" class="m-0 text-sm text-error" role="alert">{{ errors.stations }}</p>
        <p v-else class="m-0 text-sm text-surface-600">A station can be in only one planned or started visit of this request at a time.</p>
      </fieldset>

      <FormField id="sv-notes" label="Notes (optional)">
        <v-textarea
          id="sv-notes"
          v-model="notes"
          auto-grow
          autocomplete="off"
          counter="2000"
          name="notes"
          placeholder="Anything the team should bring or know"
          rows="2"
        />
      </FormField>

      <p class="m-0 text-sm text-surface-600">Everyone attending and the client are told. Needs a connection.</p>

      <div class="flex flex-wrap justify-end gap-2">
        <v-btn class="text-primary" variant="text" @click="requestClose">Cancel</v-btn>
        <v-btn color="primary" :loading="busy" type="submit">Schedule visit</v-btn>
      </div>
    </form>

    <DiscardConfirm v-model="askLeave" message="Your plan will be lost." @leave="leave" />
  </ModalSheet>
</template>

<script lang="ts" setup>
  import type { ScheduleErrors, ScheduleValues } from './visits'
  import type { RequestDetail, StaffOut, VisitOut } from '@/api/models'
  import { mdiClose, mdiPlus, mdiStar, mdiStarOutline } from '@mdi/js'
  import { computed, reactive, ref, watch } from 'vue'
  import { visitsApi } from '@/api/operations'
  import { useFormDialog } from '@/app/composables/useFormDialog'
  import { newId } from '@/app/ids'
  import DiscardConfirm from '@/components/DiscardConfirm.vue'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import FormField from '@/components/FormField.vue'
  import ModalSheet from '@/components/ModalSheet.vue'
  import { useSessionStore } from '@/stores/session'
  import { useStationDirectory } from '@/stores/stationDirectory'
  import { failureOf } from './failures'
  import { isLive, utcToZoned, validateSchedule, withoutPerson, zonedToUtc, zoneLabel } from './visits'

  // Schedule visit (PRD VIS-1; AFD J5 step 3; W10-1, W10-3, W10-5): dates in the first station's
  // zone, the people attending with one lead, and one owner for each station that goes. The server
  // checks everything again; this asks for what it needs and says why it refuses.
  const props = defineProps<{
    request: Pick<RequestDetail, 'id' | 'ref' | 'stations' | 'assigned_staff'>
  }>()

  const emit = defineEmits<{ done: [visit: VisitOut], changed: [] }>()
  const open = defineModel<boolean>({ required: true })

  const session = useSessionStore()
  const directory = useStationDirectory()

  const staff = ref<StaffOut[]>([])
  const loadingStaff = ref(false)
  const busy = ref(false)
  const problem = ref<string | null>(null)
  const addOpen = ref(false)
  const notes = ref('')
  /** station id -> the ref of the live visit that already has it */
  const taken = ref<Record<string, string>>({})
  const errors = ref<ScheduleErrors>({})
  // Made when the dialog opens: sending the same visit again after a lost answer returns it (rule 9)
  let visitId = newId()
  let initial = ''

  const values = reactive<ScheduleValues>({ start: '', end: '', staffIds: [], leadId: null, owners: {} })

  const attending = computed(() => values.staffIds.flatMap(id => staff.value.find(p => p.id === id) ?? []))
  const remaining = computed(() => staff.value.filter(p => !values.staffIds.includes(p.id)))
  const ownerItems = computed(() => attending.value.map(p => ({
    id: p.id,
    label: p.id === values.leadId ? `${p.name} (lead)` : p.name,
  })))

  // The zone the dates are written in: the first station that goes (else the request's first)
  const zone = computed(() => {
    const chosen = props.request.stations.find(s => s.id in values.owners) ?? props.request.stations[0]
    const found = directory.stations.find(s => s.id === chosen?.id)?.time_zone
    return found ?? Intl.DateTimeFormat().resolvedOptions().timeZone
  })
  const zoneName = computed(() => zoneLabel(zone.value))

  const { askLeave, requestClose, leave } = useFormDialog(open, () => snapshot() !== initial && !busy.value)

  function snapshot (): string {
    return JSON.stringify([values, notes.value])
  }

  function roleLabel (roles: readonly string[]): string {
    return roles.includes('admin') ? 'Admin' : 'Technician'
  }

  function add (id: string): void {
    values.staffIds.push(id)
    values.leadId ??= id
    addOpen.value = false
  }

  function remove (id: string): void {
    Object.assign(values, withoutPerson({ ...values, staffIds: [...values.staffIds], owners: { ...values.owners } }, id))
  }

  function toggleStation (id: string, on: boolean): void {
    if (on) {
      const owner = values.leadId ?? values.staffIds[0]
      if (owner) {
        values.owners[id] = owner
      }
    } else {
      delete values.owners[id]
    }
  }

  function defaults (): void {
    // Tomorrow, 08:00 to 16:00, on the clock of the station's zone
    const tomorrow = utcToZoned(new Date(Date.now() + 86_400_000).toISOString(), zone.value).slice(0, 10)
    values.start = `${tomorrow}T08:00`
    values.end = `${tomorrow}T16:00`
    const me = session.user?.id
    // The people on the request who can attend; else the person scheduling
    const assigned = props.request.assigned_staff.map(p => p.id).filter(id => staff.value.some(p => p.id === id))
    const self = me && staff.value.some(p => p.id === me) ? [me] : []
    values.staffIds = assigned.length > 0 ? assigned : self
    values.leadId = me && values.staffIds.includes(me) ? me : (values.staffIds[0] ?? null)
    values.owners = {}
    for (const station of props.request.stations) {
      if (!taken.value[station.id] && values.leadId) {
        values.owners[station.id] = values.leadId
      }
    }
    notes.value = ''
  }

  async function load (): Promise<void> {
    loadingStaff.value = true
    try {
      const [people, live] = await Promise.all([
        visitsApi.staff(),
        visitsApi.list({ request_id: props.request.id, limit: 200 }),
        session.user ? directory.load(session.user.id) : Promise.resolve(),
      ])
      staff.value = people.items
      const map: Record<string, string> = {}
      for (const visit of live.items.filter(v => isLive(v.status))) {
        for (const station of visit.stations) {
          map[station.station_id] = visit.ref
        }
      }
      taken.value = map
      defaults()
      initial = snapshot()
    } catch (error) {
      problem.value = failureOf(error, 'We couldn’t load the staff list. Close this and try again.').message
    } finally {
      loadingStaff.value = false
    }
  }

  // Immediate: a page may create this dialog already open
  watch(open, isOpen => {
    if (isOpen) {
      visitId = newId()
      problem.value = null
      errors.value = {}
      staff.value = []
      taken.value = {}
      void load()
    }
  }, { immediate: true })

  async function submit (): Promise<void> {
    if (busy.value) {
      return
    }
    errors.value = validateSchedule(values, zone.value)
    if (Object.keys(errors.value).length > 0) {
      return
    }
    busy.value = true
    problem.value = null
    try {
      const visit = await visitsApi.schedule({
        id: visitId,
        request_id: props.request.id,
        planned_start: zonedToUtc(values.start, zone.value)!,
        planned_end: zonedToUtc(values.end, zone.value)!,
        staff_ids: values.staffIds,
        lead_staff_id: values.leadId,
        stations: Object.entries(values.owners).map(([station_id, owner_staff_id]) => ({ station_id, owner_staff_id })),
        notes: notes.value.trim() || null,
      })
      open.value = false
      emit('done', visit)
    } catch (error) {
      const failure = failureOf(error, 'We couldn’t schedule the visit. Try again in a moment.')
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
