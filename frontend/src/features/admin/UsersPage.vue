<template>
  <PageBody>
    <div class="flex flex-col gap-4">
      <div class="flex flex-wrap items-center gap-2">
        <div aria-label="Filter by status" class="flex flex-wrap gap-2" role="group">
          <button
            v-for="f in filters"
            :key="f.value"
            :aria-pressed="filter === f.value"
            class="h-8 rounded-full border px-3 text-sm font-medium tabular-nums"
            :class="filter === f.value ? 'border-primary bg-primary-50 text-primary' : 'border-surface-200 bg-surface text-surface-700 hover:bg-surface-100'"
            type="button"
            @click="filter = f.value"
          >
            {{ f.label }} {{ count(f.value) }}
          </button>
        </div>

        <v-btn class="ml-auto" color="primary" :prepend-icon="mdiPlus" @click="openInvite">Invite user</v-btn>
      </div>

      <FeedbackBanner v-if="loadError" type="error">{{ loadError }}</FeedbackBanner>

      <div v-if="loading" aria-label="Loading users…" class="flex flex-col gap-2" role="status">
        <v-skeleton-loader v-for="n in 4" :key="n" type="list-item-two-line" />
      </div>

      <div v-else-if="!loadError" class="overflow-x-auto rounded-card border border-surface-200 bg-surface">
        <table class="w-full border-collapse text-sm">
          <thead>
            <tr class="bg-surface-100 text-left">
              <th class="px-4 py-3 text-xs font-medium text-surface-700" scope="col">Name</th>
              <th class="px-4 py-3 text-xs font-medium text-surface-700" scope="col">Status</th>
              <th class="px-4 py-3 text-xs font-medium text-surface-700" scope="col">Roles</th>
              <th class="px-4 py-3 text-xs font-medium text-surface-700" scope="col">Organization</th>
              <th class="px-4 py-3 text-right text-xs font-medium text-surface-700" scope="col">Last login</th>
            </tr>
          </thead>

          <tbody>
            <tr v-for="row in shown" :key="row.id" class="h-14 border-t border-surface-200 hover:bg-surface-100">
              <td class="px-4 py-2">
                <span class="font-medium text-surface-900">{{ row.name }}</span><br>
                <span class="text-surface-600">{{ row.email }}</span>
              </td>

              <td class="px-4"><AccountStatusChip :status="row.status" /></td>

              <td class="px-4">
                <span class="flex flex-wrap gap-1">
                  <span
                    v-for="role in row.roles"
                    :key="role"
                    class="inline-flex h-6 items-center rounded-md bg-surface-100 px-2 text-xs font-medium text-surface-700"
                  >{{ roleLabel(role) }}</span>
                </span>
              </td>

              <td class="px-4 text-surface-900">{{ orgName(row.org_id) }}</td>

              <td class="whitespace-nowrap px-4 text-right tabular-nums text-surface-900">
                {{ row.last_login_at ? when(row.last_login_at) : 'Never' }}
              </td>
            </tr>

            <tr v-if="shown.length === 0">
              <td class="px-4 py-8 text-center text-surface-600" colspan="5">No users with this status.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Invite user (AUTH-6): staff accounts are always created this way -->
    <v-navigation-drawer
      v-model="drawer"
      aria-labelledby="invite-h"
      location="end"
      tag="aside"
      temporary
      :width="440"
    >
      <form class="flex h-full flex-col" novalidate @submit.prevent="invite">
        <div class="flex items-center gap-2 border-b border-surface-200 py-4 pl-6 pr-4">
          <h2 id="invite-h" class="m-0 grow text-h2 text-surface-900">Invite user</h2>

          <v-btn
            aria-label="Close"
            icon
            size="40"
            variant="text"
            @click="drawer = false"
          >
            <v-icon class="text-surface-600" :icon="mdiClose" size="20" />
          </v-btn>
        </div>

        <div class="flex grow flex-col gap-4 overflow-y-auto p-6">
          <p class="m-0 text-sm text-surface-600">They get an email with a link to set their password. The link works for 7 days.</p>
          <FeedbackBanner v-if="actionError" type="error">{{ actionError }}</FeedbackBanner>

          <FormField id="invite-name" label="Name">
            <v-text-field id="invite-name" v-model="form.name" autocomplete="off" :error-messages="errors.name" />
          </FormField>

          <FormField id="invite-email" label="Email">
            <v-text-field
              id="invite-email"
              v-model="form.email"
              autocomplete="off"
              :error-messages="errors.email"
              spellcheck="false"
              type="email"
            />
          </FormField>

          <fieldset class="m-0 flex flex-col gap-2 border-0 p-0">
            <legend class="mb-2 p-0 text-label text-surface-900">Role</legend>

            <label v-for="role in roleChoices" :key="role.value" class="flex cursor-pointer items-start gap-3">
              <input
                v-model="form.role"
                class="mt-1 size-4 accent-primary"
                name="role"
                type="radio"
                :value="role.value"
              >

              <span class="flex flex-col">
                <span class="font-medium text-surface-900">{{ role.label }}</span>
                <span class="text-sm text-surface-600">{{ role.help }}</span>
              </span>
            </label>
          </fieldset>

          <FormField v-if="form.role === 'client'" id="invite-org" label="Organization">
            <v-autocomplete
              id="invite-org"
              v-model="form.orgId"
              :error-messages="errors.org_id"
              item-title="name"
              item-value="id"
              :items="activeOrgs"
              no-data-text="No organization by that name"
            />
          </FormField>

          <FormField id="invite-phone" label="Phone (optional)">
            <v-text-field
              id="invite-phone"
              v-model="form.phone"
              autocomplete="off"
              :error-messages="errors.phone"
              type="tel"
            />
          </FormField>
        </div>

        <div class="flex justify-end gap-2 border-t border-surface-200 px-6 py-4">
          <v-btn class="text-primary" variant="text" @click="drawer = false">Cancel</v-btn>
          <v-btn color="primary" :loading="busy" type="submit">Send invitation</v-btn>
        </div>
      </form>
    </v-navigation-drawer>

    <v-snackbar v-model="toast.show" location="bottom" :timeout="6000">{{ toast.text }}</v-snackbar>
  </PageBody>
</template>

<script lang="ts" setup>
  import type { OrgOut, Role, UserOut } from '@/api/models'
  import { mdiClose, mdiPlus } from '@mdi/js'
  import { storeToRefs } from 'pinia'
  import { computed, onMounted, reactive, ref } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { orgsApi, usersApi } from '@/api/auth'
  import { ApiError, NetworkError } from '@/api/problem'
  import { focusFirstError } from '@/app/composables/focusFirstError'
  import { formatDateTime } from '@/app/format'
  import AccountStatusChip from '@/components/AccountStatusChip.vue'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import FormField from '@/components/FormField.vue'
  import PageBody from '@/components/PageBody.vue'
  import { useSessionStore } from '@/stores/session'

  // /admin/users (AUTH-6, AUTH-11). Pending registrations live on /admin/registrations.
  type Filter = 'all' | 'active' | 'invited' | 'disabled'
  const LISTED: ReadonlySet<string> = new Set(['active', 'invited', 'disabled'])

  const { user } = storeToRefs(useSessionStore())
  const users = ref<UserOut[]>([])
  const orgs = ref<OrgOut[]>([])
  const loading = ref(true)
  const loadError = ref<string | null>(null)
  // The filter lives in the URL (?status=invited), so a reload or a shared link keeps it.
  const route = useRoute()
  const router = useRouter()
  const filter = computed<Filter>({
    get: () => {
      const value = route.query.status
      return typeof value === 'string' && LISTED.has(value) ? value as Filter : 'all'
    },
    set: value => {
      void router.replace({ query: { ...route.query, status: value === 'all' ? undefined : value } })
    },
  })

  const drawer = ref(false)
  const busy = ref(false)
  const actionError = ref<string | null>(null)
  const errors = ref<Record<string, string>>({})
  const form = reactive({ name: '', email: '', role: 'technician' as Role, orgId: null as string | null, phone: '' })
  const toast = reactive({ show: false, text: '' })

  const filters: { value: Filter, label: string }[] = [
    { value: 'all', label: 'All' },
    { value: 'active', label: 'Active' },
    { value: 'invited', label: 'Invited' },
    { value: 'disabled', label: 'Disabled' },
  ]
  const roleChoices: { value: Role, label: string, help: string }[] = [
    { value: 'technician', label: 'Technician', help: 'Claims requests, carries out visits, writes reports' },
    { value: 'admin', label: 'Admin', help: 'Everything a technician can do, plus approvals and admin pages' },
    { value: 'viewer', label: 'Viewer', help: 'Sees everything, changes nothing' },
    { value: 'client', label: 'Client', help: 'Sees their own organization’s stations and requests' },
  ]

  // Everyone but pending and rejected registrations, which belong to the Registrations page.
  const listed = computed(() => users.value.filter(u => LISTED.has(u.status)))
  const shown = computed(() => filter.value === 'all' ? listed.value : listed.value.filter(u => u.status === filter.value))
  const activeOrgs = computed(() => orgs.value.filter(o => o.status === 'active'))
  const orgNames = computed(() => new Map(orgs.value.map(o => [o.id, o.name])))

  function count (value: Filter): number {
    return value === 'all' ? listed.value.length : listed.value.filter(u => u.status === value).length
  }

  function roleLabel (role: string): string {
    return roleChoices.find(r => r.value === role)?.label ?? role
  }

  function orgName (id: string | null): string {
    return id ? (orgNames.value.get(id) ?? '—') : '—'
  }

  function when (iso: string): string {
    return formatDateTime(iso, user.value?.time_zone)
  }

  async function load (): Promise<void> {
    loading.value = true
    loadError.value = null
    try {
      const all: UserOut[] = []
      let after: string | undefined
      // Pages of 200 until the end: a few hundred accounts at most (PRD §2).
      do {
        const page = await usersApi.list({ limit: 200, after })
        all.push(...page.items)
        after = page.next_after ?? undefined
      } while (after)
      users.value = all
      orgs.value = (await orgsApi.list()).items
    } catch (error) {
      loadError.value = error instanceof NetworkError
        ? 'This needs a connection. It will load when you have signal.'
        : 'We couldn’t load the users. Reload the page to try again.'
    } finally {
      loading.value = false
    }
  }

  function openInvite (): void {
    Object.assign(form, { name: '', email: '', role: 'technician', orgId: null, phone: '' })
    errors.value = {}
    actionError.value = null
    drawer.value = true
  }

  function check (): boolean {
    const found: Record<string, string> = {}
    if (!form.name.trim()) {
      found.name = 'Enter their name'
    }
    if (!/^[^@\s]+@[^@\s]+\.[^@\s.]{2,}$/.test(form.email.trim())) {
      found.email = 'Enter a valid email'
    }
    if (form.role === 'client' && !form.orgId) {
      found.org_id = 'Choose their organization'
    }
    errors.value = found
    return Object.keys(found).length === 0
  }

  async function invite (): Promise<void> {
    actionError.value = null
    if (busy.value) {
      return
    }
    if (!check()) {
      await focusFirstError()
      return
    }
    busy.value = true
    try {
      const created = await usersApi.invite({
        name: form.name.trim(),
        email: form.email.trim(),
        roles: [form.role],
        org_id: form.role === 'client' ? form.orgId : null,
        phone: form.phone.trim() || null,
      })
      users.value = [created, ...users.value]
      drawer.value = false
      toast.text = `Invitation sent to ${created.email}.`
      toast.show = true
    } catch (error) {
      if (error instanceof ApiError && error.code === 'email_taken') {
        errors.value = { email: 'An account with this email already exists' }
      } else if (error instanceof ApiError && error.status === 422) {
        errors.value = error.fieldErrors()
        if (Object.keys(errors.value).length === 0) {
          actionError.value = error.detail
        }
      } else if (error instanceof NetworkError) {
        actionError.value = 'This needs a connection. Try again when you have signal.'
      } else {
        actionError.value = 'Something went wrong on our side. Try again in a minute.'
      }
    } finally {
      busy.value = false
    }
  }

  onMounted(load)
</script>
