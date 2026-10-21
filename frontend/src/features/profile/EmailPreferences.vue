<template>
  <div class="flex flex-col gap-5">
    <p class="m-0 text-sm text-surface-600">
      Choose which updates also reach you by email. Everything still appears in the app.
      Comments and live updates are in the app only.
    </p>

    <FeedbackBanner v-if="problem" type="error">{{ problem }}</FeedbackBanner>

    <div v-if="!prefs && !problem" aria-label="Loading email preferences…" role="status">
      <v-skeleton-loader type="list-item-two-line, list-item-two-line" />
    </div>

    <section v-for="group in prefs?.groups ?? []" :key="group.label" :aria-labelledby="`ep-${group.label}`" class="flex flex-col">
      <h3 :id="`ep-${group.label}`" class="m-0 mb-1 text-label text-surface-900">{{ group.label }}</h3>

      <div v-for="item in group.items" :key="item.key" class="flex min-h-16 items-center gap-4 border-t border-surface-200 py-2 first:border-t-0">
        <div class="grow">
          <label class="font-medium text-surface-900" :for="`ep-${item.key}`">{{ item.label }}</label>
          <p :id="`ep-${item.key}-help`" class="m-0 text-sm text-surface-600">{{ item.hint }}</p>
        </div>

        <v-switch
          :id="`ep-${item.key}`"
          :aria-describedby="`ep-${item.key}-help`"
          color="primary"
          :disabled="saving === item.key"
          hide-details
          inset
          :model-value="item.email"
          role="switch"
          @update:model-value="set(item.key, $event === true)"
        />
      </div>
    </section>

    <p aria-live="polite" class="m-0 min-h-5 text-sm text-surface-600" role="status">{{ saved ? 'Saved' : '' }}</p>
  </div>
</template>

<script lang="ts" setup>
  import type { Preferences } from '@/api/models'
  import { onMounted, ref } from 'vue'
  import { notificationsApi } from '@/api/notifications'
  import { ApiError, NetworkError } from '@/api/problem'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'

  // Which notifications also go by email (PRD NOT-4). Each switch saves as it is turned, and
  // shows only the types this person can be emailed about. Account emails are always sent and
  // are shown next to this, locked on (NOT-3). Needs a connection (OFF-10).
  const prefs = ref<Preferences | null>(null)
  const problem = ref<string | null>(null)
  const saving = ref<string | null>(null)
  const saved = ref(false)

  function words (error: unknown, what: string): string {
    return error instanceof NetworkError
      ? 'This needs a connection. Try again when you have signal.'
      : (error instanceof ApiError && error.status < 500 ? error.detail : `We couldn’t ${what}. Try again in a moment.`)
  }

  async function load (): Promise<void> {
    try {
      prefs.value = await notificationsApi.preferences()
    } catch (error) {
      problem.value = words(error, 'load your email preferences')
    }
  }

  async function set (key: string, on: boolean): Promise<void> {
    saving.value = key
    saved.value = false
    problem.value = null
    try {
      prefs.value = await notificationsApi.savePreferences({ [key]: on })
      saved.value = true
    } catch (error) {
      problem.value = words(error, 'save that')
      await load() // show what is really stored
    } finally {
      saving.value = null
    }
  }

  onMounted(load)
</script>
