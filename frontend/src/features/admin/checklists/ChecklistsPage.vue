<template>
  <PageBody
    :back="routeId ? { name: 'admin-checklists' } : undefined"
    back-label="Back to checklist templates"
    :record="routeId"
    :title="routeId ? (creating ? 'New template' : (shown?.name ?? 'Checklist template')) : 'Checklist templates'"
    wide
  >
    <template v-if="routeId && (creating || shown)" #subtitle>
      <template v-if="creating">
        <span>Choose what it is for, add the items, then save it as version 1.</span>
      </template>

      <template v-else-if="shown">
        <span class="inline-flex h-5.5 items-center rounded-md bg-surface-100 px-2 text-xs font-medium text-surface-700">{{ scopeLabel(shown) }}</span>
        <span>Version {{ shown.version }}, saved {{ formatDate(shown.created_at) }}</span>
        <span v-if="dirty" class="inline-flex items-center gap-1.5 text-surface-900"><span aria-hidden="true" class="size-2 rounded-full bg-primary" />Changes not saved</span>
      </template>
    </template>

    <template v-if="routeId && (creating || shown)" #actions>
      <v-menu v-if="!creating && current && current.version > 1">
        <template #activator="{ props: menu }">
          <v-btn
            v-bind="menu"
            :append-icon="mdiChevronDown"
            class="text-primary"
            variant="outlined"
          >Versions</v-btn>
        </template>

        <v-list aria-label="Versions" density="compact">
          <v-list-item
            v-for="n in versionNumbers"
            :key="n"
            :active="shown?.version === n"
            :title="n === current.version ? `Version ${n} (current)` : `Version ${n}`"
            :to="versionLink(n)"
          />
        </v-list>
      </v-menu>

      <v-btn v-if="dirty && !viewingOld" class="text-primary" variant="text" @click="discard">Discard</v-btn>

      <v-btn
        color="primary"
        :disabled="!canSave"
        :loading="saving"
        @click="save"
      >{{ saveLabel }}</v-btn>
    </template>

    <!-- The pane: every template, with what it is for and which version is current -->
    <PaneContent>
      <div class="flex flex-col gap-3 px-3">
        <v-btn block color="primary" :prepend-icon="mdiPlus" :to="{ name: 'admin-checklists', params: { id: 'new' } }">New template</v-btn>

        <v-text-field
          v-model="search"
          aria-label="Search templates"
          autocomplete="off"
          class="[&_.v-field]:bg-surface-50"
          clearable
          flat
          hide-details
          name="q"
          placeholder="Search templates"
          :prepend-inner-icon="mdiMagnify"
          spellcheck="false"
          type="search"
          variant="solo-inverted"
        />

        <FeedbackBanner v-if="listError" type="error">{{ listError }}</FeedbackBanner>

        <div v-else-if="listLoading" aria-label="Loading templates…" class="flex flex-col gap-2" role="status">
          <v-skeleton-loader v-for="n in 3" :key="n" type="list-item-two-line" />
        </div>

        <p v-else-if="templates.length === 0" class="m-0 px-2 text-sm text-surface-600">
          No templates yet. A technician gets the items of the template for the station’s type, so start with one for your most common type.
        </p>

        <p v-else-if="listed.length === 0" class="m-0 px-2 text-sm text-surface-600">No template matches.</p>

        <ul v-else aria-label="Checklist templates" class="m-0 flex list-none flex-col gap-0.5 p-0">
          <li v-for="row in listed" :key="row.id" class="relative">
            <router-link
              :aria-current="row.id === routeId ? 'page' : undefined"
              class="flex flex-col gap-1 rounded-card px-3 py-2.5 no-underline transition-colors duration-150"
              :class="row.id === routeId ? 'bg-primary-100 text-primary-900' : 'text-surface-900 hover:bg-surface-100'"
              :to="{ name: 'admin-checklists', params: { id: row.id } }"
            >
              <span class="truncate font-semibold" :class="row.active ? '' : 'text-surface-600'">{{ row.name }}</span>

              <span class="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-xs" :class="row.id === routeId ? '' : 'text-surface-700'">
                <span class="inline-flex h-5.5 items-center rounded-md bg-surface-100 px-2 text-xs font-medium text-surface-700">{{ scopeLabel(row) }}</span>
                <span>Version {{ row.version }}</span>
                <span v-if="row.active">{{ itemCount(row.items.length) }}</span>
                <span v-else class="inline-flex h-5.5 items-center rounded-md bg-surface-100 px-2 text-xs font-medium text-surface-700">Inactive</span>
              </span>
            </router-link>
          </li>
        </ul>
      </div>
    </PaneContent>

    <!-- The view -->
    <div v-if="!routeId" class="flex max-w-xl flex-col gap-2 py-2 text-surface-700">
      <p class="m-0">Pick a template in the list to read or change it, or make a new one.</p>
      <p class="m-0 text-sm text-surface-600">A template is a list of things to check. Each visit gets the list for its station’s type, plus an add-on for each sensor model installed there.</p>
    </div>

    <template v-else>
      <FeedbackBanner v-if="loadError" type="error">{{ loadError }}</FeedbackBanner>

      <div v-else-if="loading" aria-label="Loading the template…" class="flex flex-col gap-3" role="status">
        <v-skeleton-loader type="heading, list-item-two-line, list-item-two-line, list-item-two-line" />
      </div>

      <div v-else-if="creating || shown" class="flex flex-col gap-5">
        <div
          v-if="viewingOld && current && shown"
          class="flex max-w-4xl flex-wrap items-center gap-3 rounded-card bg-primary-100 px-4 py-3 text-primary-900"
          role="status"
        >
          <v-icon :icon="mdiHistory" size="20" />
          <span><b class="font-semibold">You are reading version {{ shown.version }}.</b> Version {{ current.version }} is the current one.</span>

          <v-btn
            class="ml-auto"
            size="small"
            :to="{ name: 'admin-checklists', params: { id: routeId } }"
            variant="flat"
          >Go to version {{ current.version }}</v-btn>
        </div>

        <FeedbackBanner v-if="saveError" type="error">
          {{ saveError }}
          <v-btn
            v-if="reloadable"
            class="ml-2"
            size="small"
            variant="outlined"
            @click="load"
          >Reload</v-btn>
        </FeedbackBanner>

        <TemplateForm
          v-model="draft"
          v-model:scope="scope"
          :applies-text="shown ? appliesTo(shown) : ''"
          :changed="changed"
          :creating="creating"
          :models="models"
          :readonly="viewingOld"
          :types="types"
        >
          <p v-if="viewingOld && current" class="m-0 max-w-4xl rounded-md bg-surface-50 px-4 py-3 text-sm text-surface-700">
            <b class="font-semibold text-surface-900">Saving this as version {{ current.version + 1 }}</b> makes it the one new visits get. Version {{ current.version }} stays in the list.
          </p>

          <p v-else-if="creating" class="m-0 max-w-4xl rounded-md bg-surface-50 px-4 py-3 text-sm text-surface-700">
            <b class="font-semibold text-surface-900">Saving writes version 1.</b> You can change it later; each save writes a new version.
          </p>

          <p v-else-if="current" class="m-0 max-w-4xl rounded-md bg-surface-50 px-4 py-3 text-sm text-surface-700">
            <b class="font-semibold text-surface-900">Saving writes version {{ current.version + 1 }}.</b> Visits that already copied version {{ current.version }} keep it; new visits get version {{ current.version + 1 }}.
          </p>
        </TemplateForm>
      </div>
    </template>

    <DiscardConfirm v-model="askLeave" message="The changes to this template will be lost." @leave="leave" />

    <v-snackbar v-model="toast.show" location="bottom" :timeout="5000">{{ toast.text }}</v-snackbar>
  </PageBody>
</template>

<script lang="ts" setup>
  import type { ChecklistTemplate } from '@/api/models'
  import { mdiChevronDown, mdiHistory, mdiMagnify, mdiPlus } from '@mdi/js'
  import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
  import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
  import { checklistsApi, sensorModelsApi } from '@/api/operations'
  import { useLeaveGuard } from '@/app/composables/useLeaveGuard'
  import { formatDate } from '@/app/format'
  import { usePaneSelection } from '@/app/shells/pane'
  import DiscardConfirm from '@/components/DiscardConfirm.vue'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import PageBody from '@/components/PageBody.vue'
  import PaneContent from '@/components/PaneContent.vue'
  import { useSessionStore } from '@/stores/session'
  import { useStationDirectory } from '@/stores/stationDirectory'
  import {
    appliesTo,
    changedKeys,
    draftOf,
    emptyScope,
    failureText,
    isDirty,
    itemCount,
    itemsForApi,
    matches,
    problemsOf,
    scopeLabel,
    typesOf,
  } from './checklists'
  import TemplateForm from './TemplateForm.vue'

  // Admin › Checklist templates (PRD VIS-8, AFD /admin/checklists, W10-11). The list is in the pane
  // and the template chosen is in the URL. Saving never changes a template: it writes the next
  // version, so an older one can still be read (`?version=`) and saved again as the newest.
  const route = useRoute()
  const router = useRouter()
  const session = useSessionStore()
  const directory = useStationDirectory()

  const routeId = computed(() => (typeof route.params.id === 'string' && route.params.id ? route.params.id : null))
  const creating = computed(() => routeId.value === 'new')
  const versionQuery = computed(() => {
    const n = Number(route.query.version)
    return Number.isInteger(n) && n > 0 ? n : null
  })
  usePaneSelection(() => routeId.value !== null)

  const templates = ref<ChecklistTemplate[]>([])
  const listLoading = ref(true)
  const listError = ref<string | null>(null)
  const search = ref('')
  const listed = computed(() => templates.value.filter(t => matches(t, search.value)))

  const current = ref<ChecklistTemplate | null>(null) // the newest version of the one open
  const shown = ref<ChecklistTemplate | null>(null) // the version on screen (an older one, or the same)
  const loading = ref(false)
  const loadError = ref<string | null>(null)
  const draft = ref(draftOf(null))
  const scope = ref(emptyScope())
  const saving = ref(false)
  const saveError = ref<string | null>(null)
  const reloadable = ref(false)
  const toast = reactive({ show: false, text: '' })
  const models = ref<{ value: string, title: string }[]>([])

  const viewingOld = computed(() => Boolean(current.value && shown.value && shown.value.version !== current.value.version))
  const types = computed(() => typesOf(directory.stations))
  const versionNumbers = computed(() => Array.from({ length: current.value?.version ?? 0 }, (_, i) => (current.value?.version ?? 0) - i))

  // What the draft is compared with: the version on screen. An older version is never "dirty"
  // (it is read only); saving it as the newest is a button of its own.
  const dirty = computed(() => !viewingOld.value && isDirty(draft.value, creating.value ? null : shown.value))
  const changed = computed(() => changedKeys(draft.value, creating.value ? null : shown.value))
  const problems = computed(() => problemsOf(draft.value, creating.value ? scope.value : undefined))
  const canSave = computed(() => !saving.value && problems.value.length === 0 && (creating.value || viewingOld.value || dirty.value))
  const saveLabel = computed(() => {
    if (creating.value) {
      return 'Save template'
    }
    return viewingOld.value ? `Save as version ${(current.value?.version ?? 0) + 1}` : 'Save version'
  })

  const { askLeave, confirmLeave, leave } = useLeaveGuard(dirty)
  onBeforeRouteLeave(confirmLeave)
  // The page's own move to the template it has just saved is not "leaving with unsaved changes"
  let redirecting = false
  onBeforeRouteUpdate((to, from) => (redirecting || (to.params.id === from.params.id && to.query.version === from.query.version) ? true : confirmLeave()))

  function warnUnload (event: BeforeUnloadEvent): void {
    if (dirty.value) {
      event.preventDefault()
    }
  }

  function versionLink (n: number) {
    return n === current.value?.version
      ? { name: 'admin-checklists', params: { id: routeId.value } }
      : { name: 'admin-checklists', params: { id: routeId.value }, query: { version: String(n) } }
  }

  function say (text: string): void {
    toast.text = text
    toast.show = true
  }

  async function loadList (): Promise<void> {
    listLoading.value = true
    try {
      templates.value = (await checklistsApi.list(true)).items
      listError.value = null
    } catch (error) {
      listError.value = failureText(error).text
    } finally {
      listLoading.value = false
    }
  }

  async function load (): Promise<void> {
    saveError.value = null
    reloadable.value = false
    loadError.value = null
    if (creating.value) {
      current.value = null
      shown.value = null
      draft.value = draftOf(null)
      scope.value = emptyScope()
      return
    }
    const id = routeId.value
    if (!id) {
      return
    }
    loading.value = true
    try {
      const newest = await checklistsApi.get(id)
      const asked = versionQuery.value
      const older = asked !== null && asked !== newest.version ? await checklistsApi.get(id, asked) : newest
      current.value = newest
      shown.value = older
      draft.value = draftOf(older)
    } catch (error) {
      current.value = null
      shown.value = null
      loadError.value = failureText(error).text
    } finally {
      loading.value = false
    }
  }

  function discard (): void {
    draft.value = draftOf(creating.value ? null : shown.value)
    if (creating.value) {
      scope.value = emptyScope()
    }
    saveError.value = null
  }

  async function save (): Promise<void> {
    if (!canSave.value) {
      return
    }
    saving.value = true
    saveError.value = null
    reloadable.value = false
    try {
      const items = itemsForApi(draft.value)
      if (creating.value) {
        const made = await checklistsApi.create({
          name: draft.value.name.trim(),
          station_type: scope.value.kind === 'type' ? scope.value.type.trim() : null,
          sensor_model_id: scope.value.kind === 'model' ? scope.value.modelId : null,
          items,
        })
        // The draft now matches the template just made, so leaving is not "unsaved"
        templates.value = [...templates.value, made]
        current.value = made
        shown.value = made
        draft.value = draftOf(made)
        redirecting = true
        try {
          await router.replace({ name: 'admin-checklists', params: { id: made.id } })
        } finally {
          redirecting = false
        }
        say('Saved as version 1.')
      } else if (current.value) {
        const saved = await checklistsApi.update(current.value.id, {
          version: current.value.version,
          name: draft.value.name.trim(),
          items,
          active: draft.value.active,
        })
        templates.value = templates.value.map(t => (t.id === saved.id ? saved : t))
        current.value = saved
        shown.value = saved
        draft.value = draftOf(saved)
        if (versionQuery.value !== null) {
          redirecting = true
          try {
            await router.replace({ name: 'admin-checklists', params: { id: saved.id } })
          } finally {
            redirecting = false
          }
        }
        say(`Saved as version ${saved.version}.`)
      }
    } catch (error) {
      const failure = failureText(error)
      saveError.value = failure.text
      reloadable.value = failure.reload
    } finally {
      saving.value = false
    }
  }

  watch([routeId, versionQuery], () => {
    void load()
  }, { immediate: true })

  onMounted(() => {
    void loadList()
    globalThis.addEventListener('beforeunload', warnUnload)
    // The station types a new template can be for, and the sensor models it can add on to
    if (session.user) {
      void directory.load(session.user.id)
    }
    void sensorModelsApi.list().then(list => {
      models.value = list.items.map(m => ({ value: m.id, title: `${m.manufacturer} ${m.model}` }))
    }).catch(() => {
      models.value = []
    })
  })

  onBeforeUnmount(() => globalThis.removeEventListener('beforeunload', warnUnload))
</script>
