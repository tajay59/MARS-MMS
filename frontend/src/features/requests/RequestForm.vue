<template>
  <form class="flex max-w-180 flex-col [&_input]:scroll-mb-24 [&_textarea]:scroll-mb-24" novalidate @submit.prevent="submit">
    <div aria-live="polite" class="mb-2 flex flex-col gap-3 empty:hidden">
      <FeedbackBanner v-if="problem === 'stale'" type="warning">
        <p class="m-0">Someone changed this request while you were editing. Load their changes, then make yours again.</p>

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
        <p class="m-0">Fix {{ summary.length }} things to {{ request ? 'save' : 'send' }}:</p>

        <ul class="m-0 mt-1 list-disc pl-5">
          <li v-for="item in summary" :key="item.key">
            <a class="text-inherit underline" :href="`#${fieldId(item.key)}`" @click.prevent="focusField(item.key)">{{ item.message }}</a>
          </li>
        </ul>
      </FeedbackBanner>

      <FeedbackBanner v-if="loadProblem" type="error">{{ loadProblem }}</FeedbackBanner>
    </div>

    <!-- An admin raises a request for an organization (REQ-2) -->
    <section v-if="isAdmin && !request" aria-labelledby="rf-org" class="flex flex-col gap-3 pb-6">
      <h2 id="rf-org" class="m-0 text-h3 text-surface-900">Organization</h2>

      <FormField :id="fieldId('orgId')" label="Raise this request for">
        <v-autocomplete
          :id="fieldId('orgId')"
          auto-select-first
          :error-messages="errors.orgId"
          item-title="name"
          item-value="id"
          :items="orgs"
          :loading="orgsLoading"
          :model-value="values.orgId"
          name="org_id"
          no-data-text="No active organizations"
          placeholder="Choose an organization"
          @update:model-value="setOrg"
        />
      </FormField>

      <FeedbackBanner type="info">An admin’s request starts as Approved, so it goes straight to the queue.</FeedbackBanner>
    </section>

    <section aria-labelledby="rf-stations" class="flex flex-col gap-3 pb-6">
      <h2 id="rf-stations" class="m-0 text-h3 text-surface-900">Stations</h2>

      <FormField :id="fieldId('stationIds')" label="Which stations is this about?">
        <v-autocomplete
          :id="fieldId('stationIds')"
          auto-select-first
          :disabled="isAdmin && !request && !values.orgId"
          :error-messages="errors.stationIds"
          :hint="stationHint"
          item-title="label"
          item-value="id"
          :items="stationItems"
          :menu-props="{ maxHeight: 320 }"
          :model-value="null"
          name="station"
          no-data-text="No station matches"
          persistent-hint
          placeholder="Search by code or name"
          @update:model-value="addStation"
        />
      </FormField>

      <ul v-if="chosen.length > 0" aria-label="Chosen stations" class="m-0 flex list-none flex-wrap gap-1.5 p-0">
        <li v-for="station in chosen" :key="station.id" class="inline-flex h-7 items-center gap-1.5 rounded-full bg-surface-100 pl-2.5 pr-1 text-surface-900">
          <span class="font-mono text-xs font-medium" translate="no">{{ station.code }}</span>
          <span class="text-sm">{{ station.name }}</span>

          <button
            :aria-label="`Remove ${station.code}`"
            class="grid size-5 place-items-center rounded-full hover:bg-surface-200"
            type="button"
            @click="removeStation(station.id)"
          >
            <v-icon :icon="mdiClose" size="14" />
          </button>
        </li>
      </ul>
    </section>

    <section aria-labelledby="rf-problem" class="flex flex-col gap-4 pb-6">
      <h2 id="rf-problem" class="m-0 text-h3 text-surface-900">Problem</h2>

      <FormField :id="fieldId('title')" label="Title">
        <v-text-field
          :id="fieldId('title')"
          v-model="values.title"
          autocomplete="off"
          :counter="MAX_TITLE"
          :error-messages="errors.title"
          :maxlength="MAX_TITLE"
          name="title"
          placeholder="What is wrong, in a few words"
        />
      </FormField>

      <FormField :id="fieldId('description')" label="Description">
        <v-textarea
          :id="fieldId('description')"
          v-model="values.description"
          auto-grow
          :error-messages="errors.description"
          name="description"
          placeholder="What happened, when it started, anything you already tried"
          rows="4"
        />
      </FormField>

      <div class="flex flex-col gap-2">
        <span id="rf-category" class="text-label text-surface-900">Category</span>
        <ChoiceGroup v-model="values.category" labelledby="rf-category" :options="CATEGORIES" />
      </div>

      <div class="flex flex-col gap-2">
        <span id="rf-priority" class="text-label text-surface-900">Priority</span>
        <ChoiceGroup v-model="values.priority" labelledby="rf-priority" :options="PRIORITIES" />
        <span class="text-sm text-surface-600">High and Urgent show in the request list. Urgent is for a station that is down and can’t wait.</span>
      </div>
    </section>

    <!-- The action bar stays in view while the form scrolls (see StationForm) -->
    <div class="sticky bottom-0 z-10 -mx-4 -mb-4 mt-2 flex flex-wrap items-center gap-3 border-t border-surface-200 bg-surface px-4 py-3 after:absolute after:inset-x-0 after:top-full after:h-12 after:bg-surface md:-mx-8 md:-mb-7 md:px-8 md:after:hidden">
      <div class="flex grow gap-2 md:grow-0">
        <v-btn class="grow md:grow-0" color="primary" :loading="busy" type="submit">{{ submitLabel }}</v-btn>
        <v-btn class="grow md:grow-0" variant="text" @click="cancel">Cancel</v-btn>
      </div>
    </div>

    <DiscardConfirm v-model="askLeave" message="What you typed will be lost." @leave="leave" />
  </form>
</template>

<script lang="ts" setup>
  import type { FieldErrors, FieldKey } from './requestFormModel'
  import type { RequestDetail, StationSummary } from '@/api/models'
  import { mdiClose } from '@mdi/js'
  import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
  import { orgsApi } from '@/api/auth'
  import { requestsApi } from '@/api/operations'
  import { ApiError, NetworkError } from '@/api/problem'
  import { useLeaveGuard } from '@/app/composables/useLeaveGuard'
  import { newId } from '@/app/ids'
  import ChoiceGroup from '@/components/ChoiceGroup.vue'
  import DiscardConfirm from '@/components/DiscardConfirm.vue'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import FormField from '@/components/FormField.vue'
  import {
    createBody,
    emptyValues,
    isUnchanged,
    MAX_STATIONS,
    MAX_TITLE,
    patchBody,
    problemOf,
    validate,
    valuesOf,
  } from './requestFormModel'
  import { CATEGORIES, PRIORITIES } from './requests'

  // New request and Edit request (PRD REQ-1, REQ-2, REQ-11): one form for both. It needs a
  // connection (OFF-10); what is typed stays on screen when a send fails. The request's ID is made
  // here, once per form, so a send that is repeated after a dropped connection can't make two.
  const props = defineProps<{
    /** The request being edited; absent for a new one. */
    request?: RequestDetail | null
    /** The stations the person may raise a request for (a client's are their organization's). */
    stations: StationSummary[]
    /** Stations to start with (from a station page or the QR landing). */
    preselect?: string[]
    isAdmin: boolean
  }>()

  const emit = defineEmits<{
    saved: [request: RequestDetail]
    cancel: []
    reload: []
  }>()

  const requestId = newId()
  const values = reactive(props.request
    ? valuesOf(props.request)
    : emptyValues((props.preselect ?? []).filter(id => props.stations.some(s => s.id === id))))
  const initial = JSON.stringify(values)
  const errors = ref<FieldErrors>({})
  const problem = ref<'stale' | 'offline' | string | null>(null)
  const loadProblem = ref<string | null>(null)
  const busy = ref(false)
  const clean = ref(false)
  const orgs = ref<{ id: string, name: string }[]>([])
  const orgsLoading = ref(false)

  const editing = computed(() => Boolean(props.request))
  const dirty = computed(() => !clean.value && JSON.stringify(values) !== initial)
  const submitLabel = computed(() => props.request ? 'Save changes' : (props.isAdmin ? 'Create request' : 'Submit request'))

  function fieldId (key: string): string {
    return `rf-${key}`
  }

  // --- Stations ---------------------------------------------------------------------------------

  /** An admin picks from the chosen organization's stations; a client's list is already theirs. */
  const available = computed(() => {
    const org = props.request?.org_id ?? values.orgId
    return props.isAdmin ? props.stations.filter(s => s.owner_org_id === org) : props.stations
  })
  const stationItems = computed(() => available.value
    .filter(s => !values.stationIds.includes(s.id))
    .map(s => ({ id: s.id, label: `${s.code} · ${s.name}` })))
  // In the order they were picked; one the person can no longer see simply drops out
  const chosen = computed(() => values.stationIds.flatMap(id => props.stations.filter(s => s.id === id)))
  const stationHint = computed(() => {
    if (props.isAdmin && !props.request && !values.orgId) {
      return 'Choose the organization first.'
    }
    return `Up to ${MAX_STATIONS} stations. Only stations of ${props.isAdmin ? 'the organization above' : 'your organization'} are listed.`
  })

  function addStation (id: string | null): void {
    if (id && !values.stationIds.includes(id) && values.stationIds.length < MAX_STATIONS) {
      values.stationIds.push(id)
    }
  }

  function removeStation (id: string): void {
    values.stationIds.splice(values.stationIds.indexOf(id), 1)
  }

  function setOrg (id: string | null): void {
    values.orgId = id
    values.stationIds = [] // the stations of one organization only
  }

  // --- Choices ----------------------------------------------------------------------------------

  async function loadOrgs (): Promise<void> {
    if (!props.isAdmin || props.request) {
      return
    }
    orgsLoading.value = true
    try {
      const active = await orgsApi.list('active')
      // A fresh array from map(): sorting it in place is safe, and toSorted needs iOS 16.
      // eslint-disable-next-line unicorn/no-array-sort
      orgs.value = active.items.map(o => ({ id: o.id, name: o.name })).sort((a, b) => a.name.localeCompare(b.name))
      // The one station a request started from names its organization
      if (!values.orgId && values.stationIds[0]) {
        const first = props.stations.find(s => s.id === values.stationIds[0])
        if (first) {
          values.orgId = first.owner_org_id
        }
      }
    } catch (error) {
      loadProblem.value = error instanceof NetworkError
        ? 'This needs a connection to list the organizations. It will load when you have signal.'
        : 'We couldn’t load the organizations. Reload the page to try again.'
    } finally {
      orgsLoading.value = false
    }
  }

  onMounted(loadOrgs)

  // --- Sending ----------------------------------------------------------------------------------

  const summary = computed(() => (Object.entries(errors.value) as [FieldKey, string][])
    .filter(([, message]) => message)
    .map(([key, message]) => ({ key, message })))

  // Fix a field and its message goes away
  watch(values, () => {
    if (Object.keys(errors.value).length > 0) {
      const now = validate(values, { admin: props.isAdmin, editing: editing.value })
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
    problem.value = null
    const found = validate(values, { admin: props.isAdmin, editing: editing.value })
    errors.value = found
    const first = (['orgId', 'stationIds', 'title', 'description'] as FieldKey[]).find(k => found[k])
    if (first) {
      await focusField(first)
      return
    }
    if (props.request && isUnchanged(values, props.request)) {
      emit('cancel')
      return
    }
    busy.value = true
    try {
      const saved = props.request
        ? await requestsApi.update(props.request.id, patchBody(values, props.request))
        : await requestsApi.create(createBody(values, requestId, { admin: props.isAdmin }))
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
        problem.value = 'We couldn’t save the request. Try again in a moment.'
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
