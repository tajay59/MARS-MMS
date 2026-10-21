<template>
  <form
    class="flex flex-col gap-2.5 rounded-2xl px-4 py-3.5"
    :class="internal ? 'bg-warning-container text-on-warning-container shadow-[inset_0_0_0_2px_var(--v-theme-warning)]' : 'bg-surface-50'"
    novalidate
    @submit.prevent="post"
  >
    <p v-if="internal" class="m-0 inline-flex items-center gap-1.5 text-sm font-semibold">
      <v-icon :icon="icons.internalComment" size="16" />Internal comment. The client will not see it or its files.
    </p>

    <FeedbackBanner v-if="problem" type="error">{{ problem }}</FeedbackBanner>

    <v-textarea
      :id="`cc-${requestId}`"
      v-model="body"
      aria-label="Write a comment"
      auto-grow
      :error-messages="bodyError ?? undefined"
      hide-details="auto"
      name="comment"
      :placeholder="internal ? 'Write a note for staff' : 'Write a comment'"
      rows="2"
      variant="outlined"
    />

    <AttachmentField compact :drafts="drafts" />

    <div class="flex flex-wrap items-center gap-x-4 gap-y-2">
      <v-switch
        v-if="isStaff"
        v-model="internal"
        color="warning"
        density="compact"
        hide-details
        inset
        label="Internal"
        role="switch"
      />

      <span class="grow" />
      <span v-if="!drafts.ready.value" class="text-sm" :class="internal ? '' : 'text-surface-600'">Post waits for the files.</span>
      <span v-else-if="isStaff" class="hidden text-sm sm:inline" :class="internal ? '' : 'text-surface-600'">PDF only, up to 25 MB each</span>
      <v-btn color="primary" :disabled="!canPost" :loading="busy" type="submit">Post</v-btn>
    </div>
  </form>
</template>

<script lang="ts" setup>
  import type { CommentOut } from '@/api/models'
  import { computed, ref } from 'vue'
  import { requestsApi } from '@/api/operations'
  import { ApiError, NetworkError } from '@/api/problem'
  import { newId } from '@/app/ids'
  import { icons } from '@/app/theme/icons'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import AttachmentField from './AttachmentField.vue'
  import { useAttachmentDrafts } from './useAttachmentDrafts'

  // Write to the thread (PRD REQ-9, REQ-10). Files go up first, under this comment's own ID, and
  // Post waits until media has checked them. The comment's ID is made here, once per comment, so
  // a send repeated after a dropped connection can't post it twice. Online only (OFF-10); what is
  // typed stays in this component's memory, never on the device's storage.
  const props = defineProps<{
    requestId: string
    isStaff: boolean
  }>()

  const emit = defineEmits<{ posted: [comment: CommentOut] }>()

  const body = ref('')
  const internal = ref(false)
  const busy = ref(false)
  const problem = ref<string | null>(null)
  const bodyError = ref<string | null>(null)
  let commentId = newId()

  const drafts = useAttachmentDrafts(() => `comment:${props.requestId}:${commentId}`)
  const canPost = computed(() => body.value.trim() !== '' && drafts.ready.value && !busy.value)

  async function post (): Promise<void> {
    if (!canPost.value) {
      return
    }
    busy.value = true
    problem.value = null
    bodyError.value = null
    try {
      const posted = await requestsApi.postComment(props.requestId, {
        id: commentId,
        body: body.value.trim(),
        internal: props.isStaff && internal.value,
        media_ids: drafts.readyIds.value,
      })
      emit('posted', posted)
      body.value = ''
      internal.value = false
      drafts.clear()
      commentId = newId()
    } catch (error) {
      if (error instanceof NetworkError) {
        problem.value = 'This needs a connection. Your comment is still here; post it when you have signal.'
      } else if (error instanceof ApiError && error.field === 'body') {
        bodyError.value = error.detail
      } else if (error instanceof ApiError && error.status < 500) {
        problem.value = error.detail
      } else {
        problem.value = 'We couldn’t post that. Try again in a moment.'
      }
    } finally {
      busy.value = false
    }
  }
</script>
