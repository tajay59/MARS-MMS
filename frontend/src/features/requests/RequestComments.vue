<template>
  <div class="flex flex-col gap-5">
    <FeedbackBanner v-if="loadError" type="error">{{ loadError }}</FeedbackBanner>

    <div v-else-if="loading" aria-label="Loading comments…" role="status">
      <v-skeleton-loader type="list-item-two-line, list-item-two-line" />
    </div>

    <template v-else>
      <p v-if="items.length === 0" class="m-0 py-6 text-center text-surface-600">
        No comments yet.{{ canPost ? ' Write the first one below.' : '' }}
      </p>

      <ol v-else aria-label="Comments, oldest first" class="m-0 flex list-none flex-col gap-5 p-0">
        <CommentItem
          v-for="comment in items"
          :key="comment.id"
          :comment="comment"
          :is-staff="isStaff"
          :now="now"
          @changed="replace"
          @stale="load"
        />
      </ol>
    </template>

    <CommentComposer v-if="canPost" :is-staff="isStaff" :request-id="requestId" @posted="added" />
  </div>
</template>

<script lang="ts" setup>
  import type { CommentOut } from '@/api/models'
  import { storeToRefs } from 'pinia'
  import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
  import { requestsApi } from '@/api/operations'
  import { NetworkError } from '@/api/problem'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import { useSessionStore } from '@/stores/session'
  import CommentComposer from './CommentComposer.vue'
  import CommentItem from './CommentItem.vue'

  // The Comments tab (PRD REQ-9, REQ-10; AFD J3 step 5): a flat thread, oldest first, and a
  // composer. A client's thread has no internal comments: the server leaves them out.
  const props = defineProps<{ requestId: string }>()
  const emit = defineEmits<{ count: [n: number] }>()

  const session = useSessionStore()
  const { roles } = storeToRefs(session)
  const isStaff = computed(() => roles.value.some(r => ['technician', 'admin', 'viewer'].includes(r)))
  // Viewers read and never post (rule 5): no composer for them, not a disabled one
  const canPost = computed(() => roles.value.some(r => r !== 'viewer'))

  const items = ref<CommentOut[]>([])
  const loading = ref(true)
  const loadError = ref<string | null>(null)
  const now = ref(new Date())
  const tick = setInterval(() => {
    now.value = new Date()
  }, 20_000)

  async function load (): Promise<void> {
    try {
      items.value = (await requestsApi.comments(props.requestId)).items
      loadError.value = null
      emit('count', items.value.length)
    } catch (error) {
      loadError.value = error instanceof NetworkError
        ? 'This needs a connection. The comments will load when you have signal.'
        : 'We couldn’t load the comments. Reload the page to try again.'
    } finally {
      loading.value = false
    }
  }

  function added (comment: CommentOut): void {
    items.value = [...items.value, comment]
    emit('count', items.value.length)
  }

  function replace (comment: CommentOut): void {
    items.value = items.value.map(c => c.id === comment.id ? comment : c)
  }

  watch(() => props.requestId, () => {
    loading.value = true
    void load()
  })
  onMounted(load)
  onBeforeUnmount(() => clearInterval(tick))
</script>
