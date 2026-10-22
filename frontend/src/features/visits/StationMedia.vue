<template>
  <div class="flex flex-col gap-3" :data-station="station.station_id">
    <div class="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-2">
      <div class="min-w-0">
        <b class="font-semibold text-surface-900">{{ station.station_name }}</b>
        <span class="ml-2 font-mono text-xs text-surface-600" translate="no">{{ station.station_code }}</span>
      </div>

      <v-btn
        v-if="canAdd"
        class="max-md:w-full"
        color="primary"
        :prepend-icon="mdiPlus"
        variant="tonal"
        @click="emit('add')"
      >Add photo or video</v-btn>
    </div>

    <FeedbackBanner v-if="problem" type="error">{{ problem }}</FeedbackBanner>

    <p v-if="phases.length === 0" class="m-0 text-sm text-surface-600">No photos or video here yet.</p>

    <section v-for="group in phases" :key="group.phase" :aria-label="`${PHASE_LABEL[group.phase]}, ${group.count}`" class="flex min-w-0 flex-col gap-2">
      <h4 class="m-0 flex items-center gap-2 text-xs font-semibold tracking-wide text-surface-700">
        {{ PHASE_LABEL[group.phase] }}
        <span class="font-medium text-surface-600">{{ group.count }}</span>
      </h4>

      <ul class="m-0 flex list-none gap-2.5 p-0 max-md:overflow-x-auto max-md:overscroll-x-contain max-md:pb-1 md:flex-wrap">
        <MediaThumb
          v-for="item in group.items"
          :key="item.media_id"
          :can-caption="canAdd"
          :can-remove="canRemoveMedia(item, me, isAdmin)"
          :item="item"
          @caption="captioning = item"
          @hide="hide(item, $event)"
          @problem="problem = $event"
          @remove="removing = item"
        />

        <PendingThumb
          v-for="item in group.pending"
          :key="item.key"
          :item="item"
          @discard="emit('discard', item.key)"
          @retry="emit('retry', item.key)"
        />
      </ul>
    </section>

    <CaptionDialog
      :item="captioning"
      :model-value="captioning !== null"
      :station-id="station.station_id"
      :visit-id="visitId"
      @done="emit('changed', $event)"
      @update:model-value="captioning = null"
    />

    <v-dialog
      aria-labelledby="rm-h"
      max-width="420"
      :model-value="removing !== null"
      role="alertdialog"
      @update:model-value="removing = null"
    >
      <div class="flex flex-col gap-4 rounded-card bg-surface p-6">
        <h2 id="rm-h" class="m-0 text-h2 text-surface-900">Remove this {{ removing?.kind === 'video' ? 'video' : 'photo' }}?</h2>
        <p class="m-0 text-surface-700">It is taken off the visit and deleted. This can’t be undone.</p>

        <div class="flex justify-end gap-2">
          <v-btn class="text-primary" variant="text" @click="removing = null">Keep it</v-btn>
          <v-btn color="error" :loading="removeBusy" @click="remove">Remove</v-btn>
        </div>
      </div>
    </v-dialog>
  </div>
</template>

<script lang="ts" setup>
  import type { VisitMedia, VisitOut, VisitStation } from '@/api/models'
  import type { PendingMedia } from '@/app/composables/useVisitMedia'
  import { mdiPlus } from '@mdi/js'
  import { computed, ref } from 'vue'
  import { visitsApi } from '@/api/operations'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import CaptionDialog from './CaptionDialog.vue'
  import { byPhase, canRemoveMedia, mediaFailure, PHASE_LABEL } from './media'
  import { forgetMedia } from './mediaLinks'
  import MediaThumb from './MediaThumb.vue'
  import PendingThumb from './PendingThumb.vue'

  // One station's photos and video on a visit, by phase, with the files still on their way (board
  // "W11 screens" 1 and 2). The changes a thumbnail's menu makes are made here; the visit as the
  // server then holds it goes back to the page.
  const props = defineProps<{
    visitId: string
    station: VisitStation
    pending: PendingMedia[]
    /** Attending staff and admins may add, caption and hide (ADR-18). */
    canAdd: boolean
    me: string
    isAdmin: boolean
  }>()

  const emit = defineEmits<{
    add: []
    retry: [key: string]
    discard: [key: string]
    changed: [visit: VisitOut]
  }>()

  const problem = ref<string | null>(null)
  const captioning = ref<VisitMedia | null>(null)
  const removing = ref<VisitMedia | null>(null)
  const removeBusy = ref(false)

  const phases = computed(() => byPhase(props.station.media)
    .map(group => ({
      ...group,
      pending: props.pending.filter(p => p.phase === group.phase),
      count: group.items.length + props.pending.filter(p => p.phase === group.phase).length,
    }))
    .filter(group => group.count > 0))

  async function hide (item: VisitMedia, hidden: boolean): Promise<void> {
    problem.value = null
    try {
      emit('changed', await visitsApi.changeMedia(props.visitId, props.station.station_id, item.media_id, { hidden }))
    } catch (error) {
      problem.value = mediaFailure(error, 'We couldn’t change that. Try again in a moment.')
    }
  }

  async function remove (): Promise<void> {
    const item = removing.value
    if (!item || removeBusy.value) {
      return
    }
    removeBusy.value = true
    problem.value = null
    try {
      const visit = await visitsApi.removeMedia(props.visitId, props.station.station_id, item.media_id)
      forgetMedia(item.media_id)
      removing.value = null
      emit('changed', visit)
    } catch (error) {
      removing.value = null
      problem.value = mediaFailure(error, 'We couldn’t remove that. Try again in a moment.')
    } finally {
      removeBusy.value = false
    }
  }
</script>
