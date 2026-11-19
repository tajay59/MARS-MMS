<template>
  <PageBody subtitle="The client organizations that own stations. Deactivating one stops its people signing in; its records are kept." wide>
    <template #actions>
      <v-btn color="primary" :prepend-icon="mdiPlus" @click="openNew">New organization</v-btn>
    </template>

    <!-- The pane: which organizations the table shows -->
    <PaneContent>
      <div aria-labelledby="org-status-h" class="flex flex-col gap-0.5 px-3" role="group">
        <h3 id="org-status-h" class="m-0 px-2 pb-1 text-sm font-semibold text-surface-900">Status</h3>

        <button
          v-for="f in ORG_FILTERS"
          :key="f.value"
          :aria-pressed="filter === f.value"
          class="flex h-10 items-center gap-3 rounded-card px-3 text-left text-sm font-medium"
          :class="filter === f.value ? 'bg-primary-50 text-primary-700 dark:text-primary' : 'text-surface-900 hover:bg-surface-100'"
          type="button"
          @click="filter = f.value"
        >
          <span class="grow">{{ f.label }}</span>
          <span class="tabular-nums text-surface-600">{{ countByStatus(orgs, f.value) }}</span>
        </button>
      </div>
    </PaneContent>

    <div class="flex flex-col gap-4">
      <FeedbackBanner v-if="loadError" type="error">{{ loadError }}</FeedbackBanner>

      <div class="w-full max-w-sm">
        <label class="sr-only" for="org-search">Search organizations</label>

        <v-text-field
          id="org-search"
          v-model="search"
          autocomplete="off"
          clearable
          placeholder="Name, short name or ID…"
          :prepend-inner-icon="mdiMagnify"
          spellcheck="false"
        />
      </div>

      <div v-if="loading" aria-label="Loading organizations…" class="flex flex-col gap-2" role="status">
        <v-skeleton-loader v-for="n in 4" :key="n" type="list-item-two-line" />
      </div>

      <template v-else-if="!loadError">
        <!-- Phones: rows as cards (DBD "Data table") -->
        <ul v-if="!mdAndUp" class="m-0 list-none p-0">
          <li v-for="org in shown" :key="org.id" class="border-t border-surface-200">
            <button class="flex min-h-18 w-full items-center gap-3 py-3 text-left" type="button" @click="openEdit(org)">
              <span class="min-w-0 grow">
                <span class="block font-medium text-surface-900">{{ org.name }}</span>
                <span class="block text-sm text-surface-600">{{ cardLine(org) }}</span>
                <span v-if="org.external_id" class="mt-0.5 block font-mono text-[13px] text-surface-600" translate="no">{{ org.external_id }}</span>
              </span>

              <OrgStatusChip :status="org.status" />
              <v-icon class="text-surface-600" :icon="mdiChevronRight" size="20" />
            </button>
          </li>
        </ul>

        <div v-else class="overflow-x-auto">
          <table class="w-full border-collapse text-sm">
            <thead>
              <tr class="bg-surface-100 text-left">
                <th class="px-4 py-3 text-xs font-medium text-surface-700" scope="col">Name</th>
                <th class="px-4 py-3 text-xs font-medium text-surface-700" scope="col">Country</th>
                <th class="px-4 py-3 text-xs font-medium text-surface-700" scope="col">ID in the earlier system</th>
                <th class="px-4 py-3 text-right text-xs font-medium text-surface-700" scope="col">People</th>
                <th class="px-4 py-3 text-xs font-medium text-surface-700" scope="col">Status</th>
                <th class="px-4 py-3" scope="col"><span class="sr-only">Stations</span></th>
              </tr>
            </thead>

            <tbody>
              <tr v-for="org in shown" :key="org.id" class="h-14 border-t border-surface-200 hover:bg-surface-100">
                <td class="px-4 py-2">
                  <button
                    class="text-left font-medium text-surface-900 hover:underline"
                    type="button"
                    @click="openEdit(org)"
                  >{{ org.name }}</button>

                  <span v-if="org.short_name" class="block text-[13px] text-surface-600">{{ org.short_name }}</span>
                </td>

                <td class="px-4 text-surface-900">{{ countryName(org.country) }}</td>

                <td class="px-4">
                  <span v-if="org.external_id" class="font-mono text-[13px] text-surface-900" translate="no">{{ org.external_id }}</span>
                  <span v-else class="text-surface-600">Not set</span>
                </td>

                <td class="px-4 text-right tabular-nums" :class="people(org) ? 'text-surface-900' : 'text-surface-600'">
                  {{ people(org) || 'None' }}
                </td>

                <td class="px-4"><OrgStatusChip :status="org.status" /></td>

                <td class="px-4 text-right">
                  <router-link
                    :aria-label="`Stations of ${org.name}`"
                    class="inline-flex min-h-6 items-center gap-0.5 font-medium text-primary hover:underline"
                    :to="{ name: 'stations', query: { org: org.id } }"
                  >Stations<v-icon :icon="mdiChevronRight" size="18" /></router-link>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <p v-if="shown.length === 0" class="m-0 py-8 text-center text-surface-600">{{ emptyText }}</p>
      </template>
    </div>

    <!-- New and edit (ORG-1), and deactivate or reactivate (ORG-4) -->
    <v-navigation-drawer
      v-model="drawerOpen"
      aria-labelledby="org-h"
      location="end"
      tag="aside"
      temporary
      :width="drawerWidth"
    >
      <form class="flex h-full flex-col" novalidate @submit.prevent="save">
        <div class="flex items-center gap-2 border-b border-surface-200 py-4 pl-6 pr-4">
          <div class="min-w-0 grow">
            <h2 id="org-h" class="m-0 truncate text-h2 text-surface-900">{{ editing ? editing.name : 'New organization' }}</h2>

            <p v-if="editing" class="m-0 mt-0.5 text-[13px] text-surface-600">
              {{ editing.status === 'active' ? 'Active' : 'Inactive' }} · {{ peopleText(people(editing)) }}
            </p>
          </div>

          <v-btn
            aria-label="Close"
            icon
            size="40"
            variant="text"
            @click="drawerOpen = false"
          >
            <v-icon class="text-surface-600" :icon="mdiClose" size="20" />
          </v-btn>
        </div>

        <div class="flex grow flex-col gap-4 overflow-y-auto overscroll-contain p-6">
          <FeedbackBanner v-if="actionError" type="error">{{ actionError }}</FeedbackBanner>

          <FormField id="org-name" label="Name">
            <v-text-field id="org-name" v-model="form.name" autocomplete="off" :error-messages="errors.name" />
          </FormField>

          <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FormField id="org-short" label="Short name (optional)">
              <v-text-field id="org-short" v-model="form.shortName" autocomplete="off" :error-messages="errors.short_name" />
            </FormField>

            <FormField id="org-country" label="Country">
              <v-autocomplete
                id="org-country"
                v-model="form.country"
                :error-messages="errors.country"
                :items="countryItems"
                no-data-text="No country by that name"
              />
            </FormField>
          </div>

          <FormField id="org-ext" label="ID in the earlier system (optional)">
            <v-text-field
              id="org-ext"
              v-model="form.externalId"
              autocomplete="off"
              class="font-mono"
              :error-messages="errors.external_id"
              hint="The station import matches stations to organizations by this ID."
              persistent-hint
              spellcheck="false"
            />
          </FormField>

          <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FormField id="org-email" label="Contact email (optional)">
              <v-text-field
                id="org-email"
                v-model="form.contactEmail"
                autocomplete="off"
                :error-messages="errors.contact_email"
                spellcheck="false"
                type="email"
              />
            </FormField>

            <FormField id="org-phone" label="Phone (optional)">
              <v-text-field
                id="org-phone"
                v-model="form.phone"
                autocomplete="off"
                :error-messages="errors.phone"
                type="tel"
              />
            </FormField>
          </div>

          <FormField id="org-address" label="Address (optional)">
            <v-textarea
              id="org-address"
              v-model="form.address"
              auto-grow
              :error-messages="errors.address"
              rows="2"
            />
          </FormField>

          <section v-if="editing" aria-labelledby="org-status-part" class="flex flex-col gap-2 border-t border-surface-200 pt-4">
            <template v-if="editing.status === 'active'">
              <h3 id="org-status-part" class="m-0 text-h3 text-surface-900">Deactivate</h3>
              <p class="m-0 text-sm text-surface-600">{{ deactivateText }}</p>

              <div>
                <v-btn class="text-error" variant="outlined" @click="confirming = true">Deactivate {{ editing.name }}</v-btn>
              </div>
            </template>

            <template v-else>
              <h3 id="org-status-part" class="m-0 text-h3 text-surface-900">Reactivate</h3>
              <p class="m-0 text-sm text-surface-600">Its people can sign in again with their own passwords.</p>

              <div>
                <v-btn class="text-primary" :loading="reactivating" variant="outlined" @click="reactivate">Reactivate {{ editing.name }}</v-btn>
              </div>
            </template>
          </section>
        </div>

        <div class="flex justify-end gap-2 border-t border-surface-200 px-6 py-4">
          <v-btn class="text-primary" variant="text" @click="drawerOpen = false">Cancel</v-btn>
          <v-btn color="primary" :loading="busy" type="submit">{{ editing ? 'Save changes' : 'Add organization' }}</v-btn>
        </div>
      </form>
    </v-navigation-drawer>

    <DeactivateOrgDialog
      v-if="editing"
      v-model="confirming"
      :org="editing"
      :people="people(editing)"
      @done="deactivated"
    />

    <DiscardConfirm v-model="askLeave" message="Your changes to this organization will be lost." @leave="leave" />

    <v-snackbar v-model="toast.show" location="bottom" :timeout="6000">{{ toast.text }}</v-snackbar>
  </PageBody>
</template>

<script lang="ts" setup>
  import type { OrgFilter, OrgForm } from './organizations'
  import type { OrgOut, UserOut } from '@/api/models'
  import { mdiChevronRight, mdiClose, mdiMagnify, mdiPlus } from '@mdi/js'
  import { computed, onMounted, reactive, ref } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { useDisplay } from 'vuetify'
  import { orgsApi, usersApi } from '@/api/auth'
  import { ApiError, NetworkError } from '@/api/problem'
  import { focusFirstError } from '@/app/composables/focusFirstError'
  import { countries, countryName } from '@/app/countries'
  import DiscardConfirm from '@/components/DiscardConfirm.vue'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import FormField from '@/components/FormField.vue'
  import PageBody from '@/components/PageBody.vue'
  import PaneContent from '@/components/PaneContent.vue'
  import DeactivateOrgDialog from './DeactivateOrgDialog.vue'
  import {
    checkForm,
    conflictField,
    countByStatus,
    emptyForm,
    formFrom,
    isOrgFilter,
    ORG_FILTERS,
    peopleByOrg,
    peopleText,
    toCreate,
    toPatch,
    visibleOrgs,
  } from './organizations'
  import OrgStatusChip from './OrgStatusChip.vue'

  // /admin/organizations (PRD ORG-1, ORG-4), from the approved "AWS-MMS Organizations screen"
  // mock-up: built like Users, with the form in a side drawer (a full-width sheet on phones).

  const route = useRoute()
  const router = useRouter()
  const { mdAndUp, width } = useDisplay()

  const orgs = ref<OrgOut[]>([])
  const users = ref<UserOut[]>([])
  const loading = ref(true)
  const loadError = ref<string | null>(null)
  const search = ref('')

  // The filter lives in the URL (?status=inactive), so a reload or a shared link keeps it
  const filter = computed<OrgFilter>({
    get: () => isOrgFilter(route.query.status) ? route.query.status : 'active',
    set: value => {
      void router.replace({ query: { ...route.query, status: value === 'active' ? undefined : value } })
    },
  })

  const shown = computed(() => visibleOrgs(orgs.value, filter.value, search.value ?? ''))
  const counts = computed(() => peopleByOrg(users.value))
  const countryItems = countries()

  const emptyText = computed(() => {
    if (search.value) {
      return 'No organization matches that search.'
    }
    return filter.value === 'inactive' ? 'No organization is inactive.' : 'No organizations yet. Add the first one.'
  })

  const drawer = ref(false)
  const askLeave = ref(false)

  // Closing with Cancel, the close button, Escape or a click outside asks first when something
  // typed would be lost (the profile page does the same)
  const dirty = computed(() => editing.value
    ? toPatch(editing.value, form) !== null
    : JSON.stringify(form) !== JSON.stringify(emptyForm()))
  const drawerOpen = computed({
    get: () => drawer.value,
    set: value => {
      if (!value && dirty.value && !busy.value) {
        askLeave.value = true
        return
      }
      drawer.value = value
    },
  })

  function leave (): void {
    askLeave.value = false
    drawer.value = false
  }
  const drawerWidth = computed(() => Math.min(440, width.value))
  const editing = ref<OrgOut | null>(null)
  const form = reactive<OrgForm>(emptyForm())
  const errors = ref<Record<string, string>>({})
  const busy = ref(false)
  const reactivating = ref(false)
  const confirming = ref(false)
  const actionError = ref<string | null>(null)
  const toast = reactive({ show: false, text: '' })

  const deactivateText = computed(() => {
    const n = editing.value ? people(editing.value) : 0
    const kept = 'Its stations, requests and reports are kept, and you can reactivate it at any time.'
    if (n === 0) {
      return `Nobody signs in for it yet. ${kept}`
    }
    const them = n === 1 ? 'Its 1 person' : `Its ${n} people`
    return `${them} can no longer sign in, and are signed out now. ${kept}`
  })

  function people (org: OrgOut): number {
    return counts.value.get(org.id) ?? 0
  }

  function cardLine (org: OrgOut): string {
    return [org.short_name, countryName(org.country), peopleText(people(org))].filter(Boolean).join(' · ')
  }

  function notify (text: string): void {
    toast.text = text
    toast.show = true
  }

  function replace (saved: OrgOut): void {
    const found = orgs.value.some(o => o.id === saved.id)
    orgs.value = found ? orgs.value.map(o => o.id === saved.id ? saved : o) : [...orgs.value, saved]
    if (editing.value?.id === saved.id) {
      editing.value = saved
    }
  }

  async function load (): Promise<void> {
    loading.value = true
    loadError.value = null
    try {
      const all: OrgOut[] = []
      let after: string | undefined
      do {
        const page = await orgsApi.list(undefined, after)
        all.push(...page.items)
        after = page.next_after ?? undefined
      } while (after)
      orgs.value = all

      const people: UserOut[] = []
      let next: string | undefined
      // Pages of 200 until the end: a few hundred accounts at most (PRD §2)
      do {
        const page = await usersApi.list({ role: 'client', limit: 200, after: next })
        people.push(...page.items)
        next = page.next_after ?? undefined
      } while (next)
      users.value = people
    } catch (error) {
      loadError.value = error instanceof NetworkError
        ? 'This needs a connection. It will load when you have signal.'
        : 'We couldn’t load the organizations. Reload the page to try again.'
    } finally {
      loading.value = false
    }
  }

  function open (org: OrgOut | null): void {
    editing.value = org
    Object.assign(form, org ? formFrom(org) : emptyForm())
    errors.value = {}
    actionError.value = null
    drawer.value = true
  }

  function openNew (): void {
    open(null)
  }

  function openEdit (org: OrgOut): void {
    open(org)
  }

  function failed (error: unknown): void {
    const field = error instanceof ApiError ? conflictField(error.code) : null
    if (field) {
      errors.value = field
    } else if (error instanceof ApiError && error.code === 'version_conflict') {
      actionError.value = 'Someone else changed this organization. Reload the page to see their change, then try again.'
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
  }

  async function save (): Promise<void> {
    actionError.value = null
    if (busy.value) {
      return
    }
    errors.value = checkForm(form)
    if (Object.keys(errors.value).length > 0) {
      await focusFirstError()
      return
    }
    busy.value = true
    try {
      if (editing.value) {
        const patch = toPatch(editing.value, form)
        if (patch) {
          replace(await orgsApi.update(editing.value.id, patch))
          notify(`${form.name.trim()} saved.`)
        }
      } else {
        const created = await orgsApi.create(toCreate(form))
        replace(created)
        notify(`${created.name} added.`)
      }
      drawer.value = false
    } catch (error) {
      failed(error)
      await focusFirstError()
    } finally {
      busy.value = false
    }
  }

  function deactivated (saved: OrgOut): void {
    replace(saved)
    drawer.value = false
    notify(`${saved.name} is deactivated. Its people are signed out.`)
  }

  async function reactivate (): Promise<void> {
    const org = editing.value
    if (!org || reactivating.value) {
      return
    }
    actionError.value = null
    reactivating.value = true
    try {
      replace(await orgsApi.update(org.id, { version: org.version, status: 'active' }))
      drawer.value = false
      notify(`${org.name} is active again.`)
    } catch (error) {
      failed(error)
    } finally {
      reactivating.value = false
    }
  }

  onMounted(load)
</script>
