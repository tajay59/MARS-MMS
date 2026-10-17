<template>
  <PageBody :subtitle="subtitle" title="My profile">
    <template #actions>
      <v-btn color="primary" :loading="busy" @click="save">Save changes</v-btn>
    </template>

    <div aria-live="polite" class="mb-6 flex flex-col gap-3 empty:hidden">
      <FeedbackBanner v-if="saved" type="success">Your changes are saved.</FeedbackBanner>
      <FeedbackBanner v-if="failure" type="error">{{ failure }}</FeedbackBanner>
    </div>

    <form class="grid items-start gap-6 lg:grid-cols-2" novalidate @submit.prevent="save">
      <div class="flex min-w-0 flex-col gap-6">
        <section aria-labelledby="details-h" class="flex flex-col gap-4 rounded-card border border-surface-200 bg-surface p-6">
          <h2 id="details-h" class="m-0 text-h3 text-surface-900">Details</h2>

          <FormField id="name" label="Name">
            <v-text-field
              id="name"
              v-model="form.name"
              autocomplete="name"
              :error-messages="errors.name"
              name="name"
            />
          </FormField>

          <div class="flex flex-col gap-1">
            <span class="text-label text-surface-900">Email</span>
            <span class="text-surface-900">{{ user?.email }}</span>
            <span class="text-sm text-surface-600">To change your email, contact the service desk.</span>
          </div>

          <FormField id="phone" label="Phone (optional)">
            <v-text-field
              id="phone"
              v-model="form.phone"
              autocomplete="tel"
              :error-messages="errors.phone"
              name="phone"
              type="tel"
            />
          </FormField>
        </section>

        <section aria-labelledby="pw-h" class="flex flex-col gap-4 rounded-card border border-surface-200 bg-surface p-6">
          <div>
            <h2 id="pw-h" class="m-0 text-h3 text-surface-900">Password</h2>
            <p class="m-0 text-sm text-surface-600">Changing it logs you out on your other devices.</p>
          </div>
          <!-- For password managers: which account this password belongs to -->
          <input autocomplete="username" hidden name="username" :value="user?.email">

          <PasswordField
            id="current-password"
            v-model="form.currentPassword"
            autocomplete="current-password"
            :error="errors.current_password"
            label="Current password"
          />

          <PasswordField
            id="new-password"
            v-model="form.newPassword"
            autocomplete="new-password"
            :error="newPasswordError"
            :hint="form.newPassword ? passwordHint : `${MIN_PASSWORD} or more characters.`"
            :hint-ok="Boolean(form.newPassword) && passwordOk"
            label="New password"
          />
        </section>
      </div>

      <div class="flex min-w-0 flex-col gap-6">
        <section aria-labelledby="tz-h" class="flex flex-col gap-4 rounded-card border border-surface-200 bg-surface p-6">
          <h2 id="tz-h" class="m-0 text-h3 text-surface-900">Time zone</h2>

          <FormField id="tz" label="Your time zone">
            <v-autocomplete
              id="tz"
              v-model="form.timeZone"
              :error-messages="errors.time_zone"
              hint="Used for times outside a station. Station pages always show the station’s own time."
              :items="zones"
              persistent-hint
            />
          </FormField>
        </section>

        <section aria-labelledby="ap-h" class="flex flex-col gap-4 rounded-card border border-surface-200 bg-surface p-6">
          <h2 id="ap-h" class="m-0 text-h3 text-surface-900">Appearance</h2>
          <AppearanceToggle labelledby="ap-h" />
          <p class="m-0 text-sm text-surface-600">System follows your device’s setting. Your choice is saved to your account.</p>
        </section>

        <section aria-labelledby="em-h" class="flex flex-col gap-4 rounded-card border border-surface-200 bg-surface p-6">
          <h2 id="em-h" class="m-0 text-h3 text-surface-900">Email preferences</h2>

          <div class="flex items-start gap-4">
            <div class="grow">
              <label class="font-medium text-surface-900" for="account-emails">Account emails</label>

              <p id="account-emails-help" class="m-0 text-sm text-surface-600">
                Approval, invitations and password resets. These are always sent.
              </p>
            </div>

            <v-switch
              id="account-emails"
              aria-describedby="account-emails-help"
              color="primary"
              disabled
              hide-details
              inset
              :model-value="true"
            />
          </div>
        </section>
      </div>

      <button class="hidden" type="submit" />
    </form>
  </PageBody>
</template>

<script lang="ts" setup>
  import type { MePatch } from '@/api/models'
  import { storeToRefs } from 'pinia'
  import { computed, onBeforeUnmount, onMounted, reactive, ref, toRef, watch } from 'vue'
  import { onBeforeRouteLeave } from 'vue-router'
  import { orgsApi } from '@/api/auth'
  import { ApiError, NetworkError } from '@/api/problem'
  import { focusFirstError } from '@/app/composables/focusFirstError'
  import { MIN_PASSWORD, usePasswordRule } from '@/app/composables/usePasswordRule'
  import AppearanceToggle from '@/components/AppearanceToggle.vue'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import FormField from '@/components/FormField.vue'
  import PageBody from '@/components/PageBody.vue'
  import PasswordField from '@/components/PasswordField.vue'
  import { useSessionStore } from '@/stores/session'

  // /profile for every role (AUTH-13; DBD D2). Viewers may edit their own profile.
  const session = useSessionStore()
  const { user, isClient } = storeToRefs(session)

  const deviceZone = Intl.DateTimeFormat().resolvedOptions().timeZone
  const zones: string[] = typeof Intl.supportedValuesOf === 'function' ? Intl.supportedValuesOf('timeZone') : ['UTC']

  const form = reactive({ name: '', phone: '', timeZone: deviceZone, currentPassword: '', newPassword: '' })
  const errors = ref<Record<string, string>>({})
  const busy = ref(false)
  const saved = ref(false)
  const tried = ref(false)
  const failure = ref<string | null>(null)
  const orgName = ref<string | null>(null)
  const { long: passwordOk, hint: passwordHint } = usePasswordRule(toRef(form, 'newPassword'), ref(undefined))

  const newPasswordError = computed(() => {
    if (errors.value.new_password) {
      return errors.value.new_password
    }
    return tried.value && form.newPassword && !passwordOk.value ? passwordHint.value : undefined
  })

  watch(user, me => {
    if (me) {
      form.name = me.name
      form.phone = me.phone ?? ''
      form.timeZone = me.time_zone ?? deviceZone
    }
  }, { immediate: true })

  const roleNames: Record<string, string> = { client: 'Client', technician: 'Technician', admin: 'Admin', viewer: 'Viewer' }
  const subtitle = computed(() => {
    const roles = (user.value?.roles ?? []).map(r => roleNames[r] ?? r).join(', ')
    return orgName.value ? `${orgName.value} · ${roles}` : roles
  })

  if (isClient.value && user.value?.org_id) {
    orgsApi.get(user.value.org_id)
      .then(org => {
        orgName.value = org.name
      })
      .catch(() => undefined)
  }

  function changes (): MePatch | null {
    const me = user.value
    if (!me) {
      return null
    }
    const patch: MePatch = {}
    if (form.name.trim() !== me.name) {
      patch.name = form.name.trim()
    }
    if (form.phone.trim() !== (me.phone ?? '')) {
      patch.phone = form.phone.trim()
    }
    if (form.timeZone && form.timeZone !== me.time_zone) {
      patch.time_zone = form.timeZone
    }
    if (form.newPassword) {
      patch.current_password = form.currentPassword
      patch.new_password = form.newPassword
    }
    return patch
  }

  // Unsaved edits: ask before leaving the page or closing the tab.
  const dirty = computed(() => Object.keys(changes() ?? {}).length > 0)
  function warnOnUnload (event: BeforeUnloadEvent): void {
    if (dirty.value) {
      event.preventDefault()
    }
  }
  onMounted(() => window.addEventListener('beforeunload', warnOnUnload))
  onBeforeUnmount(() => window.removeEventListener('beforeunload', warnOnUnload))
  onBeforeRouteLeave(() => !dirty.value || window.confirm('Leave without saving your changes?'))

  async function save (): Promise<void> {
    tried.value = true
    saved.value = false
    failure.value = null
    errors.value = {}
    if (busy.value) {
      return
    }
    if (!form.name.trim()) {
      errors.value = { name: 'Enter your name' }
      await focusFirstError()
      return
    }
    if (form.newPassword && !passwordOk.value) {
      await focusFirstError()
      return
    }
    const patch = changes()
    if (!patch) {
      return
    }
    if (Object.keys(patch).length === 0) {
      saved.value = true
      return
    }
    busy.value = true
    try {
      await session.updateProfile(patch)
      form.currentPassword = ''
      form.newPassword = ''
      tried.value = false
      saved.value = true
    } catch (error) {
      if (error instanceof ApiError && error.status === 422) {
        errors.value = error.fieldErrors()
        if (Object.keys(errors.value).length === 0) {
          failure.value = error.detail
        }
        await focusFirstError()
      } else if (error instanceof NetworkError) {
        failure.value = 'No connection. Your changes aren’t saved yet. Try again when you have signal.'
      } else {
        failure.value = 'Something went wrong on our side. Try again in a minute.'
      }
    } finally {
      busy.value = false
    }
  }
</script>
