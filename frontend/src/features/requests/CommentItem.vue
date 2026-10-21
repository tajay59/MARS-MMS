<template>
  <li
    class="flex gap-3"
    :class="comment.internal ? 'rounded-2xl bg-warning-container px-4 py-3.5 text-on-warning-container md:-mx-1' : ''"
  >
    <UserAvatar :name="comment.author.name" :seed="comment.author.id" size="sm" />

    <div class="flex min-w-0 grow flex-col gap-1.5">
      <div class="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
        <span class="font-semibold" :class="comment.internal ? '' : 'text-surface-900'">{{ comment.author.name }}</span>
        <span class="rounded-full px-2 py-px text-xs" :class="comment.internal ? 'bg-black/10' : 'bg-surface-100 text-surface-700'">{{ roleText }}</span>
        <time class="text-sm" :class="comment.internal ? '' : 'text-surface-600'" :datetime="comment.created_at">{{ formatDateTime(comment.created_at) }}</time>
        <span v-if="comment.edited_at" class="text-sm" :class="comment.internal ? '' : 'text-surface-600'">edited</span>

        <span v-if="comment.internal" class="inline-flex items-center gap-1 text-sm font-semibold">
          <v-icon :icon="icons.internalComment" size="16" />Internal, not visible to the client
        </span>
      </div>

      <!-- Editing: the text, and for staff who may see it -->
      <form v-if="editing" class="flex flex-col gap-2" novalidate @submit.prevent="save">
        <v-textarea
          v-model="draft"
          aria-label="Your comment"
          auto-grow
          :error-messages="error ?? undefined"
          hide-details="auto"
          name="body"
          rows="2"
        />

        <v-switch
          v-if="isStaff"
          v-model="draftInternal"
          color="primary"
          density="compact"
          hide-details
          inset
          label="Internal"
          role="switch"
        />

        <div class="flex gap-2">
          <v-btn
            color="primary"
            :disabled="!changed"
            :loading="busy"
            size="small"
            type="submit"
          >Save</v-btn>

          <v-btn size="small" variant="text" @click="editing = false">Cancel</v-btn>
        </div>
      </form>

      <template v-else>
        <p class="m-0 wrap-break-word whitespace-pre-line">{{ comment.body }}</p>

        <ul v-if="comment.attachments.length > 0" aria-label="Files" class="m-0 flex list-none flex-wrap gap-1.5 p-0">
          <li v-for="file in comment.attachments" :key="file.media_id" class="max-w-full">
            <SavedFile :file="file" :link="() => linkFor(file.media_id)" />
          </li>
        </ul>

        <button
          v-if="left"
          class="inline-flex items-center gap-1 self-start rounded-md py-1 text-sm font-medium text-primary hover:underline"
          type="button"
          @click="startEdit"
        >
          <v-icon :icon="mdiPencilOutline" size="16" />Edit · {{ left }}
        </button>
      </template>
    </div>
  </li>
</template>

<script lang="ts" setup>
  import type { CommentOut } from '@/api/models'
  import { mdiPencilOutline } from '@mdi/js'
  import { computed, ref } from 'vue'
  import { requestsApi } from '@/api/operations'
  import { ApiError, NetworkError } from '@/api/problem'
  import { formatDateTime } from '@/app/format'
  import { icons } from '@/app/theme/icons'
  import UserAvatar from '@/components/UserAvatar.vue'
  import { editLeft } from './attachments'
  import SavedFile from './SavedFile.vue'

  // One comment in the thread (PRD REQ-9, REQ-10). An internal one is amber, labelled, and only
  // ever sent to staff. The author can change the text for 15 minutes; staff can also flip Internal.
  const props = defineProps<{
    comment: CommentOut
    isStaff: boolean
    /** Ticks along, so "12 minutes left" counts down and the Edit link goes away on time. */
    now: Date
  }>()

  const emit = defineEmits<{ changed: [comment: CommentOut], stale: [] }>()

  const editing = ref(false)
  const draft = ref('')
  const draftInternal = ref(false)
  const busy = ref(false)
  const error = ref<string | null>(null)

  const roleText = computed(() => ({ client: 'Client', technician: 'Technician', admin: 'Admin' }[props.comment.author_role] ?? 'Staff'))
  const left = computed(() => editLeft(props.comment.editable_until, props.now))
  const changed = computed(() => draft.value.trim() !== props.comment.body
    || (props.isStaff && draftInternal.value !== props.comment.internal))

  function linkFor (mediaId: string): Promise<{ url: string }> {
    return requestsApi.commentFile(props.comment.request_id, props.comment.id, mediaId)
  }

  function startEdit (): void {
    draft.value = props.comment.body
    draftInternal.value = props.comment.internal
    error.value = null
    editing.value = true
  }

  async function save (): Promise<void> {
    if (!changed.value || busy.value) {
      return
    }
    if (!draft.value.trim()) {
      error.value = 'Write something'
      return
    }
    busy.value = true
    error.value = null
    try {
      const body: { version: number, body?: string, internal?: boolean } = { version: props.comment.version }
      if (draft.value.trim() !== props.comment.body) {
        body.body = draft.value.trim()
      }
      if (props.isStaff && draftInternal.value !== props.comment.internal) {
        body.internal = draftInternal.value
      }
      emit('changed', await requestsApi.editComment(props.comment.request_id, props.comment.id, body))
      editing.value = false
    } catch (error_) {
      if (error_ instanceof NetworkError) {
        error.value = 'This needs a connection. What you typed is still here.'
      } else if (error_ instanceof ApiError && error_.code === 'edit_window_closed') {
        error.value = 'The 15 minutes are over, so this comment is fixed now.'
        emit('stale')
      } else if (error_ instanceof ApiError && error_.status === 409) {
        error.value = 'This comment changed. It has been reloaded.'
        emit('stale')
      } else {
        error.value = 'We couldn’t save that. Try again in a moment.'
      }
    } finally {
      busy.value = false
    }
  }
</script>
