<template>
  <InstallSteps v-if="canPrepare && online && needsInstall" />

  <section v-else-if="canPrepare || (offline && prep.state.value === 'ready')" aria-labelledby="prep-h" class="flex flex-col gap-3 rounded-card bg-surface-50 p-4">
    <div class="flex items-center gap-2">
      <h2 id="prep-h" class="m-0 grow text-h3 text-surface-900">Prepare for field</h2>

      <span v-if="prep.state.value === 'ready' && prep.gaps.value.length === 0" class="inline-flex items-center gap-1.5 rounded-full bg-success-container px-2.5 py-1 text-sm font-semibold text-on-success-container">
        <v-icon :icon="mdiCheck" size="16" />Ready offline
      </span>

      <span v-else-if="prep.state.value === 'ready'" class="inline-flex items-center gap-1.5 rounded-full bg-warning-container px-2.5 py-1 text-sm font-semibold text-on-warning-container">
        <v-icon :icon="mdiAlertOutline" size="16" />Ready, {{ prep.gaps.value.length }} {{ prep.gaps.value.length === 1 ? 'file' : 'files' }} missing
      </span>
    </div>

    <FeedbackBanner v-if="prep.failure.value" type="error">{{ prep.failure.value }}</FeedbackBanner>

    <!-- Downloading -->
    <div v-if="prep.running.value && prep.progress.value" class="flex flex-col gap-3">
      <p class="m-0 font-semibold text-surface-900" role="status">Downloading {{ Math.min(prep.progress.value.filesDone + 1, prep.progress.value.filesTotal) }} of {{ prep.progress.value.filesTotal || '…' }} files</p>

      <v-progress-linear
        aria-label="Download progress"
        color="primary"
        height="8"
        :indeterminate="!prep.progress.value.bytesTotal"
        :model-value="percent"
        rounded
      />

      <p class="m-0 flex justify-between text-sm text-surface-700 tabular-nums">
        <span>{{ prep.bytes(prep.progress.value.bytesDone) }} of {{ prep.bytes(prep.progress.value.bytesTotal) }}</span>
        <span>{{ percent }}%</span>
      </p>

      <p v-if="prep.progress.value.current" class="m-0 truncate font-mono text-sm text-surface-700" translate="no">{{ prep.progress.value.current }}</p>

      <FeedbackBanner type="warning">
        Keep {{ APP_NAME }} open until this finishes. The screen stays on. A phone stops downloading when you leave the app.
      </FeedbackBanner>

      <v-btn variant="outlined" @click="prep.stop">Stop</v-btn>
    </div>

    <!-- Ready (or ready with gaps) -->
    <div v-else-if="prep.state.value === 'ready' && prep.row.value" class="flex flex-col gap-3">
      <p class="m-0 text-surface-900">Prepared {{ ago }}.</p>

      <dl class="m-0 grid grid-cols-3 gap-2 text-center">
        <div class="rounded-card bg-surface-100 px-1 py-2.5"><dd class="m-0 text-xl font-semibold text-surface-900">{{ visit.stations.length }}</dd><dt class="text-xs text-surface-700">stations</dt></div>
        <div class="rounded-card bg-surface-100 px-1 py-2.5"><dd class="m-0 text-xl font-semibold text-surface-900">{{ prep.row.value.files_done }}</dd><dt class="text-xs text-surface-700">files</dt></div>
        <div class="rounded-card bg-surface-100 px-1 py-2.5"><dd class="m-0 text-xl font-semibold text-surface-900">{{ prep.bytes(prep.storedBytes.value) }}</dd><dt class="text-xs text-surface-700">on this phone</dt></div>
      </dl>

      <FeedbackBanner v-if="prep.changed.value" type="warning">
        <strong class="block">This visit changed since you prepared.</strong>
        An owner, the dates or the status moved. Update the copy on your phone.
      </FeedbackBanner>

      <template v-if="prep.gaps.value.length > 0">
        <p class="m-0 text-surface-900">These documents did not download:</p>

        <ul class="m-0 flex list-none flex-col gap-2 p-0" role="list">
          <li v-for="file in prep.gaps.value" :key="file.media_id" class="rounded-card bg-surface-100 px-3 py-2.5 text-sm">
            <span class="font-mono" translate="no">{{ file.name }}</span>
            <span class="text-surface-700"> · {{ prep.bytes(file.size) }}</span>
          </li>
        </ul>
      </template>

      <p v-if="!offline" class="m-0 text-sm text-surface-700">
        With no signal, scan a station label or open the station from Stations. Unlock with your PIN if the app restarts.
      </p>

      <template v-if="!offline">
        <v-btn
          :color="prep.changed.value || prep.gaps.value.length > 0 ? 'primary' : undefined"
          :variant="prep.changed.value || prep.gaps.value.length > 0 ? 'flat' : 'outlined'"
          @click="prep.start"
        >{{ prep.gaps.value.length > 0 ? 'Try again' : 'Update offline copy' }}</v-btn>
      </template>
    </div>

    <!-- Started, but the configuration files did not all come -->
    <div v-else-if="prep.state.value === 'incomplete'" class="flex flex-col gap-3">
      <p class="m-0 text-surface-900">The visit is only partly on your phone: the configuration files did not all arrive. Prepare again to finish.</p>
      <v-btn color="primary" :disabled="!online" @click="prep.start">Try again</v-btn>
    </div>

    <!-- Not prepared -->
    <div v-else-if="!offline" class="flex flex-col gap-3">
      <p class="m-0 text-surface-900">Download this visit to the phone so you can work with no signal. You need a connection now.</p>

      <div class="rounded-card bg-surface-100 p-3 text-sm text-surface-900">
        <p class="m-0 font-semibold">Always included</p>

        <p class="m-0 text-surface-700">
          The request, {{ visit.stations.length === 1 ? 'the station' : `all ${visit.stations.length} stations` }}, their sensors and calibration, the boards and the latest configuration files{{ prep.configFiles.value.count ? ` (${prep.configFiles.value.count} ${prep.configFiles.value.count === 1 ? 'file' : 'files'}, ${prep.bytes(prep.configFiles.value.size)})` : '' }}.
        </p>
      </div>

      <fieldset v-if="prep.choices.value.length > 0" class="m-0 flex min-w-0 flex-col border-0 p-0">
        <legend class="mb-1 p-0 text-sm font-semibold text-surface-900">Documents to keep on the phone</legend>

        <label v-for="choice in prep.choices.value" :key="choice.media_id" class="flex min-h-12 items-center gap-3 text-surface-900">
          <input
            :checked="prep.ticked.value.has(choice.media_id)"
            class="size-5 accent-primary"
            type="checkbox"
            @change="prep.toggle(choice.media_id, ($event.target as HTMLInputElement).checked)"
          >

          <span class="min-w-0 grow break-all font-mono text-sm" translate="no">{{ choice.name }}</span>
          <span class="shrink-0 text-sm text-surface-700 tabular-nums">{{ prep.bytes(choice.size) }}</span>
        </label>

        <p class="m-0 mt-1 text-sm text-surface-700">Over 10 MB starts unticked. About {{ prep.bytes(prep.estimate.value) }} will download.</p>
      </fieldset>

      <FeedbackBanner v-if="prep.askingMobileData.value" type="warning">
        This is about {{ prep.bytes(prep.estimate.value) }} on mobile data. Tap Prepare for field again to go ahead.
      </FeedbackBanner>

      <v-btn color="primary" size="large" @click="prep.start">Prepare for field</v-btn>
    </div>

    <p v-else class="m-0 text-surface-900">This visit is not prepared on this phone. Prepare it with a connection before you go.</p>
  </section>

  <PinDialog v-model="prep.askingPin.value" @saved="prep.pinSaved" />
</template>

<script lang="ts" setup>
  import type { VisitOut } from '@/api/models'
  import { mdiAlertOutline, mdiCheck } from '@mdi/js'
  import { computed, toRef } from 'vue'
  import { APP_NAME } from '@/app/brand'
  import { mustInstallToPrepare } from '@/app/pwa/platform'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import PinDialog from '@/features/field/PinDialog.vue'
  import { preparedAgo } from '@/features/offline/preparedAgo'
  import { useSessionStore } from '@/stores/session'
  import InstallSteps from './InstallSteps.vue'
  import { usePrepare } from './usePrepare'

  // OFF-1, AFD J5 step 4: the panel on a planned or started visit for the people attending. Keyed
  // by the visit in the parent, so it reads one visit's copy on the phone for its whole life.
  const props = defineProps<{ visit: VisitOut }>()
  const session = useSessionStore()
  const prep = usePrepare(toRef(props, 'visit'))
  const online = prep.online
  const offline = computed(() => session.offline || !online.value)

  const needsInstall = mustInstallToPrepare()

  // The people attending (and an admin) prepare a planned or started visit, online
  const canPrepare = computed(() => {
    const me = session.user
    if (!me || session.isClient || !session.canAct || session.offline) {
      return false
    }
    const open = props.visit.status === 'planned' || props.visit.status === 'started'
    const attending = session.isAdmin || props.visit.staff.some(p => p.id === me.id)
    return open && attending
  })

  const percent = computed(() => {
    const p = prep.progress.value
    return p && p.bytesTotal > 0 ? Math.min(100, Math.round((p.bytesDone / p.bytesTotal) * 100)) : 0
  })

  const ago = computed(() => (prep.row.value ? preparedAgo(prep.row.value.prepared_at) : ''))
</script>
