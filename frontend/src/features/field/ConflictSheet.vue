<template>
  <ModalSheet v-model="open" labelledby="cs-h" max-width="460" persistent>
    <div class="flex flex-col gap-4">
      <!-- The work and why the server did not take it -->
      <template v-if="mode === 'detail'">
        <h2 id="cs-h" class="m-0 text-h2 text-surface-900">{{ concern.what }}</h2>
        <p class="m-0 text-surface-900">{{ concern.text }}</p>

        <section v-if="concern.element" aria-label="Your copy on this phone" class="flex flex-col gap-1.5 rounded-card border-2 border-primary bg-surface p-3.5">
          <p class="m-0 text-xs font-bold tracking-wide text-primary">YOUR COPY · ON THIS PHONE</p>
          <p class="m-0 font-semibold text-surface-900">{{ concern.element.title }}</p>
          <p v-if="concern.element.description" class="m-0 text-sm text-surface-700">{{ concern.element.description }}</p>
          <p class="m-0 text-sm text-surface-600">Saved {{ savedAt(concern.element.updated_at) }}<template v-if="files"> · {{ files }}</template></p>
        </section>

        <section v-if="concern.current" aria-label="The server’s copy" class="flex flex-col gap-1.5 rounded-card bg-surface-50 p-3.5">
          <p class="m-0 text-xs font-bold tracking-wide text-surface-700">ON THE SERVER · {{ concern.current.created_by.name.toUpperCase() }}</p>
          <p class="m-0 font-semibold text-surface-900">{{ concern.current.title }}</p>
          <p v-if="concern.current.description" class="m-0 text-sm text-surface-700">{{ concern.current.description }}</p>
          <p class="m-0 text-sm text-surface-600">Version {{ concern.current.version }}</p>
        </section>

        <p v-if="concern.canExport" class="m-0 text-sm text-surface-700">
          Nothing is merged. Export your copy, then add what you need to the server’s record when you have signal.
        </p>

        <div class="flex flex-wrap justify-end gap-2">
          <v-btn v-if="concern.canExport" color="primary" @click="startExport">Export</v-btn>
          <v-btn v-if="concern.canRetry" variant="outlined" @click="retry">Try again</v-btn>
          <v-btn class="text-primary" variant="text" @click="mode = 'confirm'">Done with this</v-btn>
          <v-btn class="text-primary" variant="text" @click="open = false">Close</v-btn>
        </div>
      </template>

      <!-- Export your work -->
      <template v-else-if="mode === 'export'">
        <h2 id="cs-h" class="m-0 text-h2 text-surface-900">Export your work</h2>

        <p class="m-0 text-surface-900">
          <template v-if="concern.station">For <strong translate="no">{{ concern.station.code }}</strong>. </template>Pass it on so it is not lost.
        </p>

        <ul v-if="built" class="m-0 flex list-none flex-col gap-1.5 p-0" role="list">
          <li class="flex justify-between rounded-lg bg-surface-50 px-3 py-2.5"><span>Written work</span><span class="text-surface-600">{{ built.summary.written }}</span></li>
          <li class="flex justify-between rounded-lg bg-surface-50 px-3 py-2.5"><span>Photos, videos and files</span><span class="text-surface-600">{{ built.summary.files }}<template v-if="built.summary.files"> · {{ megabytes(built.summary.bytes) }}</template></span></li>
        </ul>

        <p class="m-0 text-sm text-surface-600">
          One file with the written work, and the photos and videos as they were taken. Share them by email, a message or a cloud folder.
        </p>

        <FeedbackBanner v-if="problem" type="error">{{ problem }}</FeedbackBanner>
        <FeedbackBanner v-else-if="delivered" type="success">{{ delivered }}</FeedbackBanner>

        <div class="flex flex-col gap-2.5">
          <v-btn
            block
            color="primary"
            :disabled="!built"
            :height="52"
            @click="send('share')"
          >Share</v-btn>

          <v-btn
            block
            :disabled="!built"
            :height="48"
            variant="outlined"
            @click="send('save')"
          >Save to this phone</v-btn>

          <v-btn block class="text-primary" variant="text" @click="mode = 'detail'">Back</v-btn>
        </div>
      </template>

      <!-- Done with this: asked once more -->
      <template v-else>
        <h2 id="cs-h" class="m-0 text-h2 text-surface-900">Remove it from this phone?</h2>

        <p class="m-0 text-surface-900">
          <template v-if="concern.canExport && !exported">You have not exported this yet. </template>Once it is removed, only an export or the server can bring it back.
        </p>

        <div class="flex flex-wrap justify-end gap-2">
          <v-btn class="text-primary" variant="text" @click="mode = 'detail'">Keep it</v-btn>
          <v-btn color="error" :loading="busy" @click="remove">Remove</v-btn>
        </div>
      </template>
    </div>
  </ModalSheet>
</template>

<script lang="ts" setup>
  import type { Concern } from '@/features/visits/local/attention'
  import type { ExportFiles } from '@/offline/exportConflict'
  import { computed, ref, watch } from 'vue'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import ModalSheet from '@/components/ModalSheet.vue'
  import { blobsFor, doneWith, retryStuck } from '@/features/visits/local/attention'
  import { syncNow } from '@/features/visits/local/syncApp'
  import { buildExport, deliver } from '@/offline/exportConflict'

  // One conflict in full (AFD §6; W14-13): both copies, no merge, and Export, Try again or Done with
  // this. The phone's copy is never removed by looking at it, only by "Remove" here.
  const props = defineProps<{ concern: Concern, start?: 'detail' | 'export' | 'confirm' }>()

  const open = defineModel<boolean>({ required: true })
  const mode = ref<'detail' | 'export' | 'confirm'>('detail')
  const built = ref<ExportFiles | null>(null)
  const exported = ref(false)
  const delivered = ref('')
  const problem = ref('')
  const busy = ref(false)

  const files = computed(() => {
    const count = props.concern.element
      ? Object.values(props.concern.element.media).reduce((sum, list) => sum + list.length, 0)
      : 0
    return count > 0 ? `${count} ${count === 1 ? 'file' : 'files'}` : ''
  })

  const savedFormat = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
  const savedAt = (iso: string): string => savedFormat.format(new Date(iso))
  const megabytes = (bytes: number): string => `${Math.max(1, Math.round(bytes / 1024 ** 2))} MB`

  watch(open, on => {
    if (on) {
      mode.value = props.start === 'confirm' ? 'confirm' : 'detail'
      built.value = null
      delivered.value = ''
      problem.value = ''
      exported.value = false
      if (props.start === 'export') {
        void startExport()
      }
    }
  }, { immediate: true })

  async function startExport (): Promise<void> {
    mode.value = 'export'
    delivered.value = ''
    problem.value = ''
    const { concern } = props
    built.value = buildExport({
      visit: { id: concern.visit_id, ref: concern.ref, title: concern.title },
      station: concern.station,
      reason: { code: concern.code, what: concern.what, text: concern.text },
      element: concern.element,
      server_copy: concern.current,
      operations: concern.ops.map(op => ({ type: op.type, created_at: op.created_at, payload: op.payload })),
      blobs: await blobsFor(concern),
      at: new Date(),
    })
  }

  async function send (how: 'share' | 'save'): Promise<void> {
    if (!built.value) {
      return
    }
    try {
      const result = await deliver(built.value, how)
      if (result === 'cancelled') {
        return
      }
      exported.value = true
      delivered.value = result === 'shared' ? 'Shared. Keep the copy on this phone until you know it arrived.' : 'Saved to this phone’s Downloads.'
    } catch {
      problem.value = 'We couldn’t export this. Try Save to this phone.'
    }
  }

  async function retry (): Promise<void> {
    await retryStuck(props.concern.ops[0]!.user_id, props.concern.visit_id)
    open.value = false
    void syncNow(true).catch(() => undefined)
  }

  async function remove (): Promise<void> {
    busy.value = true
    try {
      await doneWith(props.concern)
      open.value = false
      // What waited behind it can go now
      void syncNow(false).catch(() => undefined)
    } finally {
      busy.value = false
    }
  }
</script>
