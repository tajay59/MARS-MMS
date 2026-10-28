<template>
  <section :aria-labelledby="headingId" class="flex min-w-0 flex-col gap-4">
    <component :is="`h${level}`" :id="headingId" class="sr-only">Changes to this {{ kind }}</component>

    <FeedbackBanner :icon="mdiLockOutline" type="info">
      <span class="text-sm">Staff only. This lists who changed what and when. The old and new values are in the audit log, which only admins can open.</span>
    </FeedbackBanner>

    <FeedbackBanner v-if="problem" type="error">
      <div class="flex flex-wrap items-center gap-3">
        <span class="grow">{{ problem }}</span>
        <v-btn size="small" variant="text" @click="load">Try again</v-btn>
      </div>
    </FeedbackBanner>

    <v-skeleton-loader v-else-if="loading" type="list-item-two-line, list-item-two-line, list-item-two-line" />
    <p v-else-if="days.length === 0" class="m-0 text-sm text-surface-600">Nothing has been recorded for this {{ kind }} yet.</p>

    <template v-else>
      <section v-for="day in days" :key="day.label" :aria-label="day.label" class="flex flex-col">
        <component :is="`h${level + 1}`" class="m-0 pb-1 pt-3 text-xs font-semibold text-surface-600">{{ day.label }}</component>

        <ul class="m-0 flex list-none flex-col p-0">
          <li v-for="e in day.entries" :key="e.seq" class="flex items-start gap-3 border-b border-surface-200 py-3 last:border-b-0">
            <UserAvatar :name="e.actor_name ?? 'System'" :seed="e.actor_name ?? 'system'" size="sm" />

            <div class="flex min-w-0 grow flex-col gap-0.5">
              <span class="break-words text-surface-900"><span class="font-semibold">{{ e.actor_name ?? 'System' }}</span> {{ e.summary }}</span>

              <span v-if="e.changed_fields.length > 0" class="flex flex-wrap items-center gap-1.5 text-xs text-surface-600">
                Changed:
                <span v-for="f in e.changed_fields" :key="f" class="rounded-full bg-surface-100 px-2 py-0.5 font-mono text-surface-800" translate="no">{{ f }}</span>
              </span>

              <span class="text-xs text-surface-600">{{ e.actor_role ? `${cap(e.actor_role)} · ` : '' }}{{ clockOf(e.at) }}</span>
            </div>

            <router-link
              v-if="admin"
              class="inline-flex min-h-6 shrink-0 items-center text-sm font-medium text-primary no-underline hover:underline"
              :to="{ name: 'admin-audit', query: { seq: String(e.seq) } }"
            >Open in audit log<span aria-hidden="true"> →</span></router-link>
          </li>
        </ul>
      </section>

      <div v-if="next !== null" class="flex justify-center">
        <v-btn :loading="loadingMore" variant="outlined" @click="more">Show earlier changes</v-btn>
      </div>
    </template>
  </section>
</template>

<script lang="ts" setup>
  import type { HistoryEntry, HistoryKind } from '@/api/models'
  import { mdiLockOutline } from '@mdi/js'
  import { computed, onMounted, ref, useId, watch } from 'vue'
  import { auditApi } from '@/api/audit'
  import { ApiError, NetworkError } from '@/api/problem'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import UserAvatar from '@/components/UserAvatar.vue'
  import { clockOf, dayOf } from '../audit/audit'

  // A page's History (PRD AUD-6): who did what to it and when, newest first, grouped by day. Staff
  // and the Viewer read it; the values are not here (W19-2), only the names of the fields that
  // changed. An admin can open the full record. It needs a connection; nothing is kept.
  // `level` is the heading level of the section, so the page's headings stay in order
  const props = withDefaults(defineProps<{ kind: HistoryKind, id: string, admin?: boolean, level?: 2 | 3 }>(), { level: 2, admin: false })

  const headingId = useId()
  const entries = ref<HistoryEntry[]>([])
  const next = ref<number | null>(null)
  const loading = ref(true)
  const loadingMore = ref(false)
  const problem = ref<string | null>(null)

  const days = computed(() => {
    const out: { label: string, entries: HistoryEntry[] }[] = []
    for (const e of entries.value) {
      const label = dayOf(e.at)
      const last = out.at(-1)
      if (last?.label === label) {
        last.entries.push(e)
      } else {
        out.push({ label, entries: [e] })
      }
    }
    return out
  })

  function cap (role: string): string {
    return role.charAt(0).toUpperCase() + role.slice(1)
  }

  function words (error: unknown): string {
    if (error instanceof NetworkError) {
      return 'The history needs a connection. Connect to the internet and try again.'
    }
    return error instanceof ApiError && error.status === 403
      ? 'Only staff can read this history.'
      : 'We couldn’t load the history. Try again.'
  }

  async function load (): Promise<void> {
    loading.value = true
    problem.value = null
    try {
      const page = await auditApi.history(props.kind, props.id)
      entries.value = page.items
      next.value = page.next_cursor
    } catch (error) {
      problem.value = words(error)
    } finally {
      loading.value = false
    }
  }

  async function more (): Promise<void> {
    if (next.value === null) {
      return
    }
    loadingMore.value = true
    try {
      const page = await auditApi.history(props.kind, props.id, next.value)
      entries.value = [...entries.value, ...page.items]
      next.value = page.next_cursor
    } catch (error) {
      problem.value = words(error)
    } finally {
      loadingMore.value = false
    }
  }

  watch(() => [props.kind, props.id], () => void load())
  onMounted(load)
</script>
