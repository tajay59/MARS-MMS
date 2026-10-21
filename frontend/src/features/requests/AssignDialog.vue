<template>
  <ModalSheet v-model="open" labelledby="as-h" max-width="520" persistent>
    <form class="flex flex-col gap-4" novalidate @submit.prevent="submit">
      <div class="flex items-start justify-between gap-3">
        <div class="min-w-0">
          <h2 id="as-h" class="m-0 text-h2 text-surface-900">{{ changing ? 'Change staff' : 'Assign staff' }}</h2>
          <p class="m-0 mt-0.5 font-mono text-xs font-medium text-surface-600" translate="no">{{ request.ref }}<template v-if="stationCode"> · {{ stationCode }}</template></p>
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

      <v-text-field
        v-model="search"
        aria-label="Search staff by name"
        autocomplete="off"
        hide-details
        name="staff-search"
        placeholder="Search by name"
        :prepend-inner-icon="mdiMagnify"
        spellcheck="false"
        type="search"
      />

      <ul v-if="chosenPeople.length > 0" aria-label="Chosen" class="m-0 flex list-none flex-wrap gap-1.5 p-0">
        <li v-for="person in chosenPeople" :key="person.id">
          <button
            :aria-label="`Remove ${person.name}`"
            class="inline-flex h-8 items-center gap-1.5 rounded-lg bg-primary-100 pl-3 pr-2 text-sm font-medium text-primary-800 dark:bg-primary-800 dark:text-primary-100"
            type="button"
            @click="toggle(person.id)"
          >{{ person.name }}<v-icon :icon="mdiClose" size="16" /></button>
        </li>
      </ul>

      <div v-if="loading" aria-label="Loading staff…" role="status">
        <v-skeleton-loader type="list-item-two-line, list-item-two-line, list-item-two-line" />
      </div>

      <p v-else-if="options.length === 0" class="m-0 py-4 text-center text-surface-600">
        {{ people.length === 0 ? 'No technicians to assign yet.' : 'Nobody has that name.' }}
      </p>

      <ul v-else aria-label="Staff" class="m-0 flex list-none flex-col border-t border-surface-200 p-0">
        <li v-for="person in options" :key="person.id" class="border-b border-surface-200">
          <label class="flex min-h-15 cursor-pointer items-center gap-3 py-2">
            <v-checkbox-btn
              density="comfortable"
              :model-value="person.chosen"
              @update:model-value="toggle(person.id)"
            />

            <UserAvatar :name="person.name" :seed="person.id" size="sm" />

            <span class="flex min-w-0 grow flex-col">
              <span class="truncate font-medium text-surface-900">{{ person.name }}</span>
              <span class="text-sm text-surface-600">{{ roleLabel(person.roles) }} · {{ openLabel(person.open) }}</span>
            </span>
          </label>
        </li>
      </ul>

      <p class="m-0 text-sm text-surface-600">
        {{ changing
          ? 'The request stays assigned. People you add are told; people you remove are told too.'
          : 'The request becomes Assigned. Everyone you choose is told, and so is the client.' }}
      </p>

      <div class="flex flex-wrap justify-end gap-2">
        <v-btn class="text-primary" variant="text" @click="requestClose">Cancel</v-btn>
        <v-btn color="primary" :disabled="!canSave" :loading="busy" type="submit">{{ saveLabel }}</v-btn>
      </div>
    </form>

    <DiscardConfirm v-model="askLeave" message="Your choice will be lost." @leave="leave" />
  </ModalSheet>
</template>

<script lang="ts" setup>
  import type { StaffPerson } from './queue'
  import type { RequestDetail } from '@/api/models'
  import { mdiClose, mdiMagnify } from '@mdi/js'
  import { computed, ref, watch } from 'vue'
  import { usersApi } from '@/api/auth'
  import { requestsApi } from '@/api/operations'
  import { ApiError, NetworkError } from '@/api/problem'
  import { useFormDialog } from '@/app/composables/useFormDialog'
  import DiscardConfirm from '@/components/DiscardConfirm.vue'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import ModalSheet from '@/components/ModalSheet.vue'
  import UserAvatar from '@/components/UserAvatar.vue'
  import { assignable, openLabel, roleLabel, sameStaff, staffOptions } from './queue'

  // Assign staff (PRD REQ-7, AFD J4 step 4): an admin picks one or more technicians or admins for an
  // approved request, or changes who is on one that is already assigned. The server checks who can
  // be assigned; this lists them with how many open requests each has.
  const props = defineProps<{
    request: Pick<RequestDetail, 'id' | 'ref' | 'version' | 'status' | 'assigned_staff'> & { stationCode?: string }
  }>()

  const emit = defineEmits<{ done: [request: RequestDetail], changed: [] }>()
  const open = defineModel<boolean>({ required: true })

  const changing = computed(() => props.request.status === 'assigned')
  const stationCode = computed(() => props.request.stationCode)
  const people = ref<StaffPerson[]>([])
  const workload = ref<Record<string, number>>({})
  const chosen = ref<string[]>([])
  const search = ref('')
  const loading = ref(false)
  const busy = ref(false)
  const problem = ref<string | null>(null)

  const original = computed(() => props.request.assigned_staff.map(p => p.id))
  const options = computed(() => staffOptions(people.value, workload.value, new Set(chosen.value), search.value))
  const chosenPeople = computed(() => chosen.value.flatMap(id => people.value.find(p => p.id === id) ?? []))
  const canSave = computed(() => chosen.value.length > 0 && !(changing.value && sameStaff(chosen.value, original.value)))
  const saveLabel = computed(() => {
    const n = chosen.value.length
    if (changing.value) {
      return 'Save staff'
    }
    return n <= 1 ? 'Assign' : `Assign ${n} people`
  })

  const { askLeave, requestClose, leave } = useFormDialog(open, () => !sameStaff(chosen.value, original.value) && !busy.value)

  function toggle (id: string): void {
    chosen.value = chosen.value.includes(id) ? chosen.value.filter(x => x !== id) : [...chosen.value, id]
  }

  async function load (): Promise<void> {
    loading.value = true
    try {
      // A person with both roles comes back from both lists; `assignable` keeps them once
      const [techs, admins, counts] = await Promise.all([
        usersApi.list({ role: 'technician', status: 'active', limit: 200 }),
        usersApi.list({ role: 'admin', status: 'active', limit: 200 }),
        requestsApi.workload(),
      ])
      people.value = assignable([...techs.items, ...admins.items])
      workload.value = counts.open_requests
    } catch (error) {
      problem.value = error instanceof NetworkError
        ? 'This needs a connection. Try again when you have signal.'
        : 'We couldn’t load the staff list. Close this and try again.'
    } finally {
      loading.value = false
    }
  }

  watch(open, isOpen => {
    if (isOpen) {
      chosen.value = [...original.value]
      search.value = ''
      problem.value = null
      void load()
    }
  })

  async function submit (): Promise<void> {
    if (!canSave.value || busy.value) {
      return
    }
    busy.value = true
    problem.value = null
    try {
      const done = await requestsApi.assign(props.request.id, chosen.value, changing.value ? props.request.version : undefined)
      open.value = false
      emit('done', done)
    } catch (error) {
      if (error instanceof NetworkError) {
        problem.value = 'This needs a connection. Your choice is still here; try again when you have signal.'
      } else if (error instanceof ApiError && (error.code === 'request_changed' || error.code === 'bad_transition' || error.status === 409)) {
        problem.value = 'Someone else just changed this request. Close this and reload to see it.'
        emit('changed')
      } else {
        problem.value = error instanceof ApiError && error.status < 500 ? error.detail : 'We couldn’t assign. Try again in a moment.'
      }
    } finally {
      busy.value = false
    }
  }
</script>
