<template>
  <PageBody
    :back="routeId ? { name: 'admin-registrations' } : undefined"
    back-label="Back to registrations"
    :record="routeId"
    :subtitle="selected ? `Registered ${when(selected.created_at)}` : undefined"
    :title="selected ? selected.name : undefined"
  >
    <!-- The pane: everyone waiting, newest last; the one chosen opens in the view -->
    <PaneContent>
      <div class="flex flex-col gap-2 px-2">
        <FeedbackBanner v-if="loadError" class="mx-2" type="error">{{ loadError }}</FeedbackBanner>

        <div v-else-if="loading" aria-label="Loading registrations…" class="flex flex-col gap-2 px-2" role="status">
          <v-skeleton-loader v-for="n in 3" :key="n" type="list-item-two-line" />
        </div>

        <p v-else-if="rows.length === 0" class="m-0 px-3 text-sm text-surface-600">No one is waiting.</p>

        <!-- A message-list row (Google Messages): avatar, name with the time on its right, the
             organization below; the open one gets the rounded highlight -->
        <ul v-else aria-label="Waiting for approval" class="m-0 flex list-none flex-col gap-1 p-0">
          <li
            v-for="row in rows"
            :key="row.id"
            class="group relative flex items-center gap-4 rounded-full py-3 pl-3 pr-5 transition-colors duration-150"
            :class="selected?.id === row.id ? 'bg-primary-50' : 'hover:bg-surface-100 active:bg-surface-200'"
            @click="keyPress"
            @pointercancel="release"
            @pointerdown="press"
            @pointerleave="release"
            @pointerup="release"
          >
            <UserAvatar class="transition-transform duration-200 ease-out group-hover:scale-105" :name="row.name" :seed="row.id" />

            <div class="flex min-w-0 grow flex-col gap-0.5">
              <div class="flex items-baseline gap-3">
                <!-- The name is the button; the whole row is its target -->
                <button
                  :aria-current="selected?.id === row.id ? 'true' : undefined"
                  class="min-w-0 grow truncate text-left text-base font-medium text-surface-900 after:absolute after:inset-0 after:rounded-full focus-visible:outline-none focus-visible:after:outline-2 focus-visible:after:outline-offset-2 focus-visible:after:outline-primary"
                  type="button"
                  @click="open(row)"
                >{{ row.name }}</button>

                <time
                  class="shrink-0 text-xs tabular-nums text-surface-600"
                  :datetime="row.created_at"
                  :title="when(row.created_at)"
                >{{ listTime(row.created_at) }}</time>
              </div>

              <span class="truncate text-sm text-surface-600">{{ row.proposed_org_name ?? 'No organization given' }}</span>
            </div>
          </li>
        </ul>
      </div>
    </PaneContent>

    <!-- The view: the registration chosen, with approve or reject (J1 steps 3–4b) -->
    <div v-if="selected" class="flex max-w-2xl flex-col gap-6">
      <dl class="m-0 grid grid-cols-[112px_1fr] gap-x-4 gap-y-2 text-sm">
        <dt class="text-surface-600">Email</dt><dd class="m-0 break-all text-surface-900">{{ selected.email }}</dd>
        <dt class="text-surface-600">Phone</dt><dd class="m-0 text-surface-900">{{ selected.phone || '—' }}</dd>
        <dt class="text-surface-600">Organization</dt><dd class="m-0 font-semibold text-surface-900">{{ selected.proposed_org_name ?? '—' }}</dd>
      </dl>

      <FeedbackBanner v-if="actionError" type="error">{{ actionError }}</FeedbackBanner>

      <fieldset v-if="mode === 'approve'" class="m-0 flex flex-col gap-3 border-0 p-0">
        <legend class="mb-1 p-0 text-h3 text-surface-900">Link to an organization</legend>

        <label
          v-if="match"
          class="flex cursor-pointer items-start gap-3 rounded-md p-3"
          :class="choice === 'match' ? 'border-2 border-primary bg-primary-50' : 'border border-surface-200'"
        >
          <input
            v-model="choice"
            class="mt-1 size-4 accent-primary"
            name="org"
            type="radio"
            value="match"
          >

          <span class="flex flex-col">
            <span class="font-medium text-surface-900">{{ match.name }}</span>
            <span class="text-sm text-surface-600">{{ countryName(match.country) }} · closest match to what they typed</span>
          </span>
        </label>

        <label
          class="flex cursor-pointer items-start gap-3 rounded-md p-3"
          :class="choice === 'existing' ? 'border-2 border-primary bg-primary-50' : 'border border-surface-200'"
        >
          <input
            v-model="choice"
            class="mt-1 size-4 accent-primary"
            name="org"
            type="radio"
            value="existing"
          >

          <span class="font-medium text-surface-900">{{ match ? 'Another existing organization' : 'An existing organization' }}</span>
        </label>

        <FormField v-if="choice === 'existing'" id="existing-org" label="Organization">
          <v-autocomplete
            id="existing-org"
            v-model="existingId"
            :error-messages="fieldError.org_id"
            item-title="name"
            item-value="id"
            :items="activeOrgs"
            no-data-text="No organization by that name"
          />
        </FormField>

        <label
          class="flex cursor-pointer items-start gap-3 rounded-md p-3"
          :class="choice === 'new' ? 'border-2 border-primary bg-primary-50' : 'border border-surface-200'"
        >
          <input
            v-model="choice"
            class="mt-1 size-4 accent-primary"
            name="org"
            type="radio"
            value="new"
          >

          <span class="flex flex-col">
            <span class="font-medium text-surface-900">A new organization</span>
            <span class="text-sm text-surface-600">You’ll set its name and country</span>
          </span>
        </label>

        <template v-if="choice === 'new'">
          <FormField id="new-org-name" label="Organization name">
            <v-text-field id="new-org-name" v-model="newOrg.name" autocomplete="off" :error-messages="fieldError.name" />
          </FormField>

          <FormField id="new-org-country" label="Country">
            <v-autocomplete
              id="new-org-country"
              v-model="newOrg.country"
              :error-messages="fieldError.country"
              :items="countries()"
            />
          </FormField>
        </template>
      </fieldset>

      <FormField v-else id="reason" label="Reason for rejecting">
        <v-textarea
          id="reason"
          v-model="reason"
          auto-grow
          autocomplete="off"
          counter="500"
          :error-messages="fieldError.reason"
          :hint="`${firstName} will receive this in the rejection email.`"
          maxlength="500"
          persistent-hint
          rows="4"
        />
      </FormField>

      <div class="flex flex-wrap justify-end gap-2 border-t border-surface-200 pt-5">
        <template v-if="mode === 'approve'">
          <v-btn class="text-primary" variant="outlined" @click="mode = 'reject'">Reject</v-btn>
          <v-btn color="primary" :loading="busy" @click="approve">Approve {{ selected.name }}</v-btn>
        </template>

        <template v-else>
          <v-btn class="text-primary" variant="text" @click="mode = 'approve'">Cancel</v-btn>
          <v-btn color="error" :loading="busy" @click="reject">Reject registration</v-btn>
        </template>
      </div>
    </div>

    <div v-else-if="routeId && !loading && !loadError" class="flex max-w-xl flex-col items-start gap-3">
      <h2 class="m-0 text-h3 text-surface-900">This registration isn’t waiting any more</h2>
      <p class="m-0 text-surface-600">Someone may have approved or rejected it already.</p>
      <v-btn class="text-primary" :to="{ name: 'admin-registrations' }" variant="outlined">See who is waiting</v-btn>
    </div>

    <div v-else-if="!loading && !loadError" class="flex max-w-xl flex-col items-start gap-2">
      <template v-if="rows.length > 0">
        <p class="m-0 text-kpi tabular-nums text-surface-900">{{ rows.length }}</p>
        <p class="m-0 text-surface-900">{{ summary }}</p>
        <p class="m-0 text-sm text-surface-600">Choose someone in the list to approve or reject them.</p>
      </template>

      <template v-else>
        <v-icon class="text-success" :icon="mdiCheckCircleOutline" size="32" />
        <h2 class="m-0 text-h3 text-surface-900">No one is waiting</h2>
        <p class="m-0 text-surface-600">New registrations appear here, and on your dashboard, as they come in.</p>
      </template>
    </div>

    <v-snackbar v-model="toast.show" location="bottom" :timeout="6000">{{ toast.text }}</v-snackbar>
  </PageBody>
</template>

<script lang="ts" setup>
  import type { ApproveIn, OrgOut, UserOut } from '@/api/models'
  import { mdiCheckCircleOutline } from '@mdi/js'
  import { storeToRefs } from 'pinia'
  import { computed, onMounted, reactive, ref, watch } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { orgsApi, usersApi } from '@/api/auth'
  import { ApiError, NetworkError } from '@/api/problem'
  import { focusFirstError } from '@/app/composables/focusFirstError'
  import { countries, countryName } from '@/app/countries'
  import { formatDateTime, formatListTime } from '@/app/format'
  import { pressDown, pressPulse, pressUp } from '@/app/motion'
  import { usePaneSelection } from '@/app/shells/pane'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import FormField from '@/components/FormField.vue'
  import PageBody from '@/components/PageBody.vue'
  import PaneContent from '@/components/PaneContent.vue'
  import UserAvatar from '@/components/UserAvatar.vue'
  import { useRegistrationsStore } from '@/stores/registrations'
  import { useSessionStore } from '@/stores/session'
  import { closestOrg } from './orgMatch'

  // /admin/registrations (AFD J1 steps 3–4b; AUTH-3). Approve links the client to an existing
  // organization or creates one; reject sends the reason by email. The person chosen is in the
  // URL (/admin/registrations/:id), so a reload or Back keeps the place.
  const { user } = storeToRefs(useSessionStore())
  const registrations = useRegistrationsStore()

  const rows = ref<UserOut[]>([])
  const orgs = ref<OrgOut[]>([])
  const loading = ref(true)
  const loadError = ref<string | null>(null)

  const route = useRoute()
  const router = useRouter()
  const routeId = computed(() => typeof route.params.id === 'string' && route.params.id ? route.params.id : null)
  const selected = computed(() => rows.value.find(r => r.id === routeId.value) ?? null)
  usePaneSelection(() => routeId.value !== null)
  const mode = ref<'approve' | 'reject'>('approve')
  const choice = ref<'match' | 'existing' | 'new'>('existing')
  const existingId = ref<string | null>(null)
  const newOrg = reactive({ name: '', country: null as string | null })
  const reason = ref('')
  const busy = ref(false)
  const actionError = ref<string | null>(null)
  const fieldError = ref<Record<string, string>>({})
  const toast = reactive({ show: false, text: '' })

  const activeOrgs = computed(() => orgs.value.filter(o => o.status === 'active'))
  const match = computed(() => selected.value?.proposed_org_name ? closestOrg(selected.value.proposed_org_name, orgs.value) : null)
  const firstName = computed(() => selected.value?.name.split(/\s+/, 1)[0] ?? 'They')
  const summary = computed(() => {
    const n = rows.value.length
    if (n === 0) {
      return ''
    }
    const who = n === 1 ? '1 person is' : `${n} people are`
    return `${who} waiting for an account. Check who they are and which organization they belong to before approving.`
  })

  function when (iso: string): string {
    return formatDateTime(iso, user.value?.time_zone)
  }

  function listTime (iso: string): string {
    return formatListTime(iso, user.value?.time_zone)
  }

  async function load (): Promise<void> {
    loading.value = true
    loadError.value = null
    try {
      const [page, orgPage] = await Promise.all([usersApi.list({ status: 'pending', limit: 200 }), orgsApi.list()])
      rows.value = page.items
      orgs.value = orgPage.items
      registrations.pending = page.items.length
    } catch (error) {
      loadError.value = error instanceof NetworkError
        ? 'This needs a connection. It will load when you have signal.'
        : 'We couldn’t load the registrations. Reload the page to try again.'
    } finally {
      loading.value = false
    }
  }

  // A row shrinks while pressed and springs back when let go (motion.ts); a keyboard click has no
  // pointer, so it gets both in one go
  function press (event: PointerEvent): void {
    if (event.button === 0) {
      pressDown(event.currentTarget as Element)
    }
  }

  function release (event: PointerEvent): void {
    pressUp(event.currentTarget as Element)
  }

  function keyPress (event: MouseEvent): void {
    if (event.detail === 0) {
      pressPulse(event.currentTarget as Element)
    }
  }

  function open (row: UserOut): void {
    void router.push({ name: 'admin-registrations', params: { id: row.id } })
  }

  // A new person in the view starts with a fresh form
  watch(selected, (row, before) => {
    if (!row || row.id === before?.id) {
      return
    }
    mode.value = 'approve'
    actionError.value = null
    fieldError.value = {}
    reason.value = ''
    existingId.value = null
    newOrg.name = row.proposed_org_name ?? ''
    newOrg.country = null
    choice.value = match.value ? 'match' : 'existing'
  }, { immediate: true })

  function body (): ApproveIn | null {
    const errors: Record<string, string> = {}
    let out: ApproveIn | null = null
    if (choice.value === 'match' && match.value) {
      out = { org_id: match.value.id }
    } else if (choice.value === 'existing') {
      if (existingId.value) {
        out = { org_id: existingId.value }
      } else {
        errors.org_id = 'Choose an organization'
      }
    } else {
      if (!newOrg.name.trim()) {
        errors.name = 'Enter the organization’s name'
      }
      if (!newOrg.country) {
        errors.country = 'Choose a country'
      }
      if (newOrg.name.trim() && newOrg.country) {
        out = { new_organization: { name: newOrg.name.trim(), country: newOrg.country } }
      }
    }
    fieldError.value = errors
    return out
  }

  async function approve (): Promise<void> {
    const target = selected.value
    const payload = body()
    if (!target || busy.value) {
      return
    }
    if (!payload) {
      await focusFirstError()
      return
    }
    await act(async () => {
      await usersApi.approve(target.id, { ...payload, version: target.version })
      done(target, `${target.name} is approved. We’ve emailed them.`)
    })
  }

  async function reject (): Promise<void> {
    const target = selected.value
    if (!target || busy.value) {
      return
    }
    if (!reason.value.trim()) {
      fieldError.value = { reason: 'Say why, so they know what to do next' }
      await focusFirstError()
      return
    }
    await act(async () => {
      await usersApi.reject(target.id, reason.value.trim())
      done(target, `${target.name}’s registration is rejected. We’ve emailed them the reason.`)
    })
  }

  async function act (work: () => Promise<void>): Promise<void> {
    busy.value = true
    actionError.value = null
    try {
      await work()
    } catch (error) {
      actionError.value = explain(error)
    } finally {
      busy.value = false
    }
  }

  function explain (error: unknown): string {
    if (error instanceof NetworkError) {
      return 'This needs a connection. Try again when you have signal.'
    }
    if (error instanceof ApiError) {
      if (error.code === 'org_name_taken') {
        fieldError.value = { name: 'An organization with this name already exists. Choose it instead.' }
        return 'That organization already exists.'
      }
      if (error.status === 409 || error.code === 'invalid_status' || error.status === 404) {
        void load()
        return 'Someone else dealt with this registration a moment ago. The list is up to date now.'
      }
      return error.detail
    }
    return 'Something went wrong on our side. Try again in a minute.'
  }

  function done (target: UserOut, message: string): void {
    rows.value = rows.value.filter(r => r.id !== target.id)
    registrations.pending = rows.value.length
    void router.replace({ name: 'admin-registrations' })
    toast.text = message
    toast.show = true
  }

  onMounted(load)
</script>
