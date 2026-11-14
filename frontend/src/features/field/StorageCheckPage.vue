<template>
  <PageBody :back="{ name: 'sync' }" title="Storage check">
    <div class="flex grow flex-col gap-4 px-4 py-4 md:mx-auto md:w-full md:max-w-xl md:px-6">
      <p class="m-0 text-surface-900">
        Test that this phone keeps big files across a restart. Add photos and videos, restart the phone, then verify. These are test files: they are never uploaded.
      </p>

      <FeedbackBanner v-if="failure" type="error">{{ failure }}</FeedbackBanner>

      <section aria-labelledby="sc-held-h" class="flex flex-col gap-3 rounded-card bg-surface-50 p-4">
        <h2 id="sc-held-h" class="m-0 text-h3 text-surface-900">Stored on this phone</h2>

        <dl class="m-0 grid grid-cols-3 gap-2 text-center">
          <div class="rounded-card bg-surface-100 px-1 py-2.5"><dd class="m-0 text-xl font-semibold text-surface-900">{{ held.photos }}</dd><dt class="text-xs text-surface-700">photos</dt></div>
          <div class="rounded-card bg-surface-100 px-1 py-2.5"><dd class="m-0 text-xl font-semibold text-surface-900">{{ held.videos }}</dd><dt class="text-xs text-surface-700">videos</dt></div>
          <div class="rounded-card bg-surface-100 px-1 py-2.5"><dd class="m-0 text-xl font-semibold text-surface-900">{{ megabytes }}</dd><dt class="text-xs text-surface-700">MB</dt></div>
        </dl>

        <input
          ref="picker"
          accept="image/*,video/*"
          aria-label="Photos and videos for the check"
          class="sr-only"
          data-testid="storage-check-files"
          multiple
          tabindex="-1"
          type="file"
          @change="add"
        >

        <v-btn :disabled="working || total >= MAX_FILES" variant="outlined" @click="picker?.click()">Add photos and videos</v-btn>
        <p class="m-0 text-sm text-surface-700">Up to {{ MAX_FILES }} files. Each one is read and fingerprinted as it is stored.</p>

        <div v-if="working" class="flex flex-col gap-2" role="status">
          <v-progress-linear
            aria-label="Progress"
            color="primary"
            height="6"
            :model-value="percent"
            rounded
          />

          <p class="m-0 text-sm text-surface-700">{{ label }} {{ done }} of {{ of }}</p>
        </div>
      </section>

      <section v-if="verdict" aria-labelledby="sc-verdict-h" class="flex flex-col gap-2 rounded-card bg-surface-50 p-4" role="status">
        <div class="flex items-center gap-2">
          <h2 id="sc-verdict-h" class="m-0 grow text-h3 text-surface-900">Last check</h2>
          <span v-if="verdict.failed.length === 0" class="rounded-full bg-success-container px-2.5 py-1 text-sm font-semibold text-on-success-container">All {{ verdict.checked }} match</span>
          <span v-else class="rounded-full bg-error-container px-2.5 py-1 text-sm font-semibold text-on-error-container">{{ verdict.failed.length }} of {{ verdict.checked }} are missing</span>
        </div>

        <p v-if="verdict.failed.length === 0" class="m-0 text-surface-900">
          Every file was read again and its fingerprint matches what was stored. Checked {{ when }}.
        </p>

        <template v-else>
          <p class="m-0 text-surface-900">These files are gone or changed. Tell the product owner: the phone does not keep big files safely (risk R4).</p>

          <ul class="m-0 flex list-none flex-col gap-1 p-0 font-mono text-sm" translate="no">
            <li v-for="name in verdict.failed" :key="name">{{ name }}</li>
          </ul>
        </template>
      </section>

      <div class="mt-auto flex gap-3 pt-2">
        <v-btn class="grow" :disabled="working || total === 0" variant="outlined" @click="remove">Remove test files</v-btn>
        <v-btn class="grow" color="primary" :disabled="working || total === 0" @click="check">Verify</v-btn>
      </div>
    </div>
  </PageBody>
</template>

<script lang="ts" setup>
  import type { Verdict } from '@/offline/storageCheck'
  import { computed, onMounted, ref } from 'vue'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import PageBody from '@/components/PageBody.vue'
  import { requestPersistence } from '@/offline/storage'
  import { addFiles, clear, MAX_FILES, stored, verify } from '@/offline/storageCheck'
  import { useSessionStore } from '@/stores/session'

  // The W13 iOS check (testing.md §5, risk R4): store photos and videos, restart, read them back. Test
  // files only, in the `diagnostic` state, which the sync of W14 must skip.
  const session = useSessionStore()
  const picker = ref<HTMLInputElement | null>(null)
  const held = ref({ photos: 0, videos: 0, other: 0, bytes: 0 })
  const verdict = ref<Verdict | null>(null)
  const working = ref(false)
  const label = ref('')
  const done = ref(0)
  const of = ref(0)
  const failure = ref('')

  const total = computed(() => held.value.photos + held.value.videos + held.value.other)
  const megabytes = computed(() => Math.round(held.value.bytes / 1024 ** 2))
  const percent = computed(() => (of.value > 0 ? Math.round((done.value / of.value) * 100) : 0))
  const when = computed(() => (verdict.value
    ? new Intl.DateTimeFormat('en-GB', { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(new Date(verdict.value.at))
    : ''))

  async function refresh (): Promise<void> {
    const id = session.user?.id
    held.value = id ? await stored(id) : { photos: 0, videos: 0, other: 0, bytes: 0 }
  }

  async function run (what: string, work: (id: string) => Promise<void>): Promise<void> {
    const id = session.user?.id
    if (!id || working.value) {
      return
    }
    working.value = true
    failure.value = ''
    label.value = what
    done.value = 0
    of.value = 0
    try {
      await work(id)
    } catch (error) {
      failure.value = error instanceof DOMException && error.name === 'QuotaExceededError'
        ? 'This phone is out of space. Remove some test files or free space, then try again.'
        : 'Something went wrong while storing the files. Try again.'
    } finally {
      working.value = false
      await refresh()
    }
  }

  function progress (n: number, count: number): void {
    done.value = n
    of.value = count
  }

  async function add (event: Event): Promise<void> {
    const input = event.target as HTMLInputElement
    const files = [...(input.files ?? [])]
    input.value = ''
    verdict.value = null
    await requestPersistence()
    await run('Storing', async id => {
      await addFiles(id, files, progress)
    })
  }

  async function check (): Promise<void> {
    await run('Reading back', async id => {
      verdict.value = await verify(id, progress)
    })
  }

  async function remove (): Promise<void> {
    await run('Removing', async id => {
      await clear(id)
      verdict.value = null
    })
  }

  onMounted(refresh)
</script>
