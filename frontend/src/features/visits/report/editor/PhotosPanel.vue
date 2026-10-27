<template>
  <section aria-labelledby="pp-h" class="flex flex-col gap-3 rounded-card border border-surface-200 bg-surface p-4">
    <div class="flex flex-col gap-1">
      <h2 id="pp-h" class="m-0 text-h4 text-surface-900">Photos in the report</h2>
      <p class="m-0 text-sm text-surface-700">Up to {{ BODY_LIMIT }} photos per station print in the body. The rest go in the appendix. A caption you change here applies to this report only.</p>
    </div>

    <div v-for="group in groups" :key="group.stationId" class="flex flex-col gap-2">
      <p class="m-0 text-sm text-surface-800">
        <span class="font-mono" translate="no">{{ group.code }}</span> ·
        {{ group.inBody }} of {{ BODY_LIMIT }} in the body<span v-if="group.full">. Move one to the appendix to put another in the body.</span>
      </p>

      <ul class="m-0 grid list-none grid-cols-[repeat(auto-fill,minmax(160px,1fr))] gap-3 p-0">
        <li v-for="photo in group.photos" :key="photo.mediaId" class="flex flex-col gap-2 rounded-md border border-surface-200 bg-surface-50 p-2">
          <div class="aspect-4/3 max-w-full overflow-hidden rounded-sm bg-surface-200">
            <img
              v-if="thumbs[photo.mediaId]"
              :alt="photo.caption || photo.filename"
              class="size-full object-cover"
              decoding="async"
              loading="lazy"
              :src="thumbs[photo.mediaId]"
            >
          </div>

          <v-text-field
            :aria-label="`Caption for ${photo.filename}`"
            density="compact"
            :disabled="!editable"
            hide-details
            :maxlength="200"
            :model-value="fields.captions[photo.mediaId] ?? ''"
            placeholder="Add a caption"
            @update:model-value="setCaption(photo.mediaId, $event)"
          />

          <v-switch
            :aria-label="`${photo.filename} in the body`"
            color="primary"
            density="compact"
            :disabled="!editable || (!fields.inBody[photo.mediaId] && group.full)"
            hide-details
            :label="fields.inBody[photo.mediaId] ? 'In the body' : (group.full ? 'Appendix · body is full' : 'Appendix')"
            :model-value="fields.inBody[photo.mediaId] ?? false"
            @update:model-value="setBody(photo.mediaId, $event === true)"
          />
        </li>
      </ul>
    </div>

    <p v-if="groups.length === 0" class="m-0 text-sm text-surface-700">No photos from shared elements.</p>
    <p v-else class="m-0 text-xs text-surface-600">Photos from staff-only elements are not listed.</p>
  </section>
</template>

<script lang="ts" setup>
  import type { Fields } from './useReportEditor'
  import { BODY_LIMIT, type PhotoGroup } from './rules'

  // The photo choice of the editor (W17, RPT-2): which photos print in each station's body, and
  // their captions in this report. The thumbnails are the page's own (`thumbs`), kept in memory.
  defineProps<{
    groups: PhotoGroup[]
    fields: Fields
    editable: boolean
    thumbs: Record<string, string | undefined>
  }>()

  const emit = defineEmits<{ caption: [mediaId: string, text: string], body: [mediaId: string, inBody: boolean] }>()

  function setCaption (mediaId: string, text: string | null): void {
    emit('caption', mediaId, text ?? '')
  }

  function setBody (mediaId: string, inBody: boolean): void {
    emit('body', mediaId, inBody)
  }
</script>
