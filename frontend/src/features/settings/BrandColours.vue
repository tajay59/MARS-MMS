<template>
  <!-- Fields keep clear of the sticky save bar when they take focus -->
  <div class="flex flex-col gap-8 [&_button]:scroll-mb-24 [&_input]:scroll-mb-24 [&_textarea]:scroll-mb-24">
    <!-- What everyone sees now, or the draft being previewed on this screen -->
    <section aria-labelledby="current-h" class="flex flex-col gap-4">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div class="min-w-0">
          <h2 id="current-h" class="m-0 text-h3 text-surface-900">{{ dirty ? 'Preview' : 'In use' }}: {{ themeName }}</h2>

          <p class="m-0 text-sm text-surface-600">
            <template v-if="dirty">Only you see this until you save it. Everyone else still sees {{ savedName }}.</template>
            <template v-else>Everyone sees these colours, on the login page too. Status colours never change.</template>
          </p>
        </div>

        <div class="flex flex-wrap gap-2">
          <v-btn class="text-primary" :prepend-icon="icons.upload" variant="outlined" @click="fileInput?.click()">Upload a theme file</v-btn>
          <v-btn class="text-primary" :prepend-icon="icons.download" variant="text" @click="download">Download</v-btn>
        </div>

        <input
          ref="fileInput"
          accept=".json,application/json"
          aria-label="Theme file (JSON)"
          class="hidden"
          type="file"
          @change="upload"
        >
      </div>

      <div class="grid gap-4 sm:grid-cols-2">
        <ThemePreview :theme="working" />
        <ThemePreview dark :theme="working" />
      </div>
    </section>

    <div aria-live="polite" class="flex flex-col gap-3 empty:hidden">
      <FeedbackBanner v-if="fileError" type="error">{{ fileError }}</FeedbackBanner>
      <FeedbackBanner v-if="saveError" type="error">{{ saveError }}</FeedbackBanner>

      <FeedbackBanner v-if="problems.length > 0" type="warning">
        <p class="m-0 font-semibold">Some text may be hard to read with these colours</p>

        <ul class="m-0 mt-1 pl-5">
          <li v-for="problem in problems" :key="problem">{{ problem }}</li>
        </ul>
      </FeedbackBanner>
    </div>

    <!-- The editor: from a seed colour, colour by colour, or as JSON -->
    <section aria-labelledby="edit-h" class="flex flex-col gap-4 border-t border-surface-200 pt-6">
      <div>
        <h2 id="edit-h" class="m-0 text-h3 text-surface-900">Change the colours</h2>
        <p class="m-0 text-sm text-surface-600">Changes show on your screen at once. Nobody else sees them until you save.</p>
      </div>

      <v-tabs v-model="tab" aria-label="Ways to change the colours" color="primary" density="compact">
        <v-tab value="seed">From one colour</v-tab>
        <v-tab value="roles">Colour by colour</v-tab>
        <v-tab value="json">JSON</v-tab>
      </v-tabs>

      <v-tabs-window v-model="tab">
        <v-tabs-window-item value="seed">
          <div class="flex max-w-xl flex-col gap-4 pt-2">
            <p class="m-0 text-sm text-surface-900">Pick the main brand colour. We make the full light and dark themes from it, the way Material Theme Builder does.</p>

            <div class="flex flex-wrap items-end gap-3">
              <FormField id="seed-hex" label="Brand colour">
                <div class="flex items-center gap-2">
                  <input
                    v-model="seed"
                    aria-label="Pick the brand colour"
                    class="h-10 w-12 cursor-pointer rounded-md border border-surface-500 bg-surface p-1"
                    type="color"
                  >

                  <v-text-field
                    id="seed-hex"
                    v-model="seedText"
                    autocomplete="off"
                    class="w-36 font-mono"
                    :error-messages="seedError"
                    maxlength="7"
                    spellcheck="false"
                  />
                </div>
              </FormField>

              <v-btn color="primary" :loading="generating" @click="generate">Make the themes</v-btn>
            </div>
          </div>
        </v-tabs-window-item>

        <v-tabs-window-item value="roles">
          <div class="flex flex-col gap-4 pt-2">
            <p class="m-0 text-sm text-surface-900">
              Fine-tune single colours. The tints for selected rows and avatars come from the palettes, which change with "From one colour" or in the JSON.
            </p>

            <div class="grid gap-x-8 gap-y-6 lg:grid-cols-2">
              <fieldset v-for="scheme in SCHEMES" :key="scheme" class="m-0 flex min-w-0 flex-col gap-1 border-0 p-0">
                <legend class="mb-2 p-0 text-label text-surface-900">{{ scheme === 'light' ? 'Light theme' : 'Dark theme' }}</legend>

                <div
                  v-for="role in shownRoles"
                  :key="role"
                  class="flex items-center gap-3 rounded-md px-1 py-1.5 hover:bg-surface-50"
                >
                  <input
                    :id="`${scheme}-${role}`"
                    class="h-8 w-10 shrink-0 cursor-pointer rounded-md border border-surface-300 bg-surface p-0.5"
                    type="color"
                    :value="working.schemes[scheme]![role]!.toLowerCase()"
                    @change="setRole(scheme, role, ($event.target as HTMLInputElement).value)"
                  >

                  <label class="flex min-w-0 grow cursor-pointer flex-col" :for="`${scheme}-${role}`">
                    <span class="truncate text-sm font-medium text-surface-900">{{ roleLabel(role) }}</span>
                    <span v-if="roleUse(scheme, role)" class="truncate text-xs text-surface-600">{{ roleUse(scheme, role) }}</span>
                  </label>

                  <span class="shrink-0 font-mono text-xs tabular-nums text-surface-600">{{ working.schemes[scheme]![role] }}</span>
                </div>
              </fieldset>
            </div>

            <div>
              <v-btn class="text-primary" variant="text" @click="allRoles = !allRoles">
                {{ allRoles ? 'Show the main colours only' : `Show all ${ROLES.length} colours` }}
              </v-btn>
            </div>
          </div>
        </v-tabs-window-item>

        <v-tabs-window-item value="json">
          <div class="flex flex-col gap-3 pt-2">
            <FormField id="theme-json" label="Theme (Material Theme Builder JSON)">
              <v-textarea
                id="theme-json"
                v-model="jsonText"
                autocomplete="off"
                class="font-mono"
                :error-messages="jsonError ?? undefined"
                rows="14"
                spellcheck="false"
              />
            </FormField>

            <div class="flex flex-wrap gap-2">
              <v-btn color="primary" variant="outlined" @click="applyJson">Preview this JSON</v-btn>
              <v-btn class="text-primary" variant="text" @click="jsonText = toExportJson(working)">Undo my typing</v-btn>
            </div>
          </div>
        </v-tabs-window-item>
      </v-tabs-window>
    </section>

    <!-- Save for everyone, or go back -->
    <div
      v-if="dirty || (branding.isCustom && !toBuiltIn)"
      class="sticky bottom-0 -mx-4 flex flex-wrap items-center justify-end gap-2 border-t border-surface-200 bg-surface px-4 py-4 md:-mx-8 md:px-8"
    >
      <v-btn
        v-if="branding.isCustom && !toBuiltIn"
        class="mr-auto text-primary"
        :prepend-icon="icons.restore"
        variant="text"
        @click="useBuiltIn"
      >Go back to the built-in colours</v-btn>

      <template v-if="dirty">
        <v-btn class="text-primary" variant="text" @click="discard">Discard changes</v-btn>
        <v-btn color="primary" :loading="saving" @click="save">{{ toBuiltIn ? 'Use the built-in colours for everyone' : 'Save for everyone' }}</v-btn>
      </template>
    </div>

    <v-snackbar v-model="toast.show" location="bottom" :timeout="6000">{{ toast.text }}</v-snackbar>

    <DiscardConfirm v-model="askLeave" message="The colours you changed will be lost." @leave="leave" />
  </div>
</template>

<script lang="ts" setup>
  import type { MaterialTheme, Role, SchemeName } from '@/app/theme/material'
  import { computed, onBeforeUnmount, onMounted, reactive, ref, shallowRef, watch } from 'vue'
  import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
  import { ApiError, NetworkError } from '@/api/problem'
  import { useLeaveGuard } from '@/app/composables/useLeaveGuard'
  import { builtInMaterial } from '@/app/theme/brand'
  import { icons } from '@/app/theme/icons'
  import { contrastProblems, parseMaterialTheme, ROLES, SCHEMES, toExportJson } from '@/app/theme/material'
  import DiscardConfirm from '@/components/DiscardConfirm.vue'
  import FeedbackBanner from '@/components/FeedbackBanner.vue'
  import FormField from '@/components/FormField.vue'
  import { useBrandingStore } from '@/stores/branding'
  import ThemePreview from './ThemePreview.vue'

  // The organization's brand colours (decision W4-12): a Material 3 theme, uploaded, made from one
  // colour or edited, previewed on this screen, then saved for everyone (PUT /api/v1/auth/branding).
  const branding = useBrandingStore()

  /** The edits not saved yet; null when the editor shows what is in use. */
  const draft = shallowRef<MaterialTheme | null>(null)
  /** The draft is "go back to the built-in colours": saving sends null. */
  const toBuiltIn = ref(false)
  const working = computed(() => draft.value ?? branding.saved.material ?? builtInMaterial)
  const dirty = computed(() => draft.value !== null)
  const savedName = computed(() => branding.saved.material?.name ?? (branding.isCustom ? 'the saved colours' : 'the built-in colours'))
  const themeName = computed(() => toBuiltIn.value ? 'Built-in' : (working.value.name ?? 'Custom colours'))
  const problems = computed(() => contrastProblems(working.value))

  const tab = ref<'seed' | 'roles' | 'json'>('seed')
  const fileInput = ref<HTMLInputElement | null>(null)
  const fileError = ref<string | null>(null)
  const saveError = ref<string | null>(null)
  const saving = ref(false)
  const generating = ref(false)
  const toast = reactive({ show: false, text: '' })

  // --- Edits ------------------------------------------------------------------------------------

  function edit (next: MaterialTheme, builtIn = false): void {
    draft.value = next
    toBuiltIn.value = builtIn
    fileError.value = null
    saveError.value = null
    branding.startPreview(next)
  }

  function discard (): void {
    draft.value = null
    toBuiltIn.value = false
    saveError.value = null
    branding.endPreview()
  }

  function useBuiltIn (): void {
    edit(builtInMaterial, true)
  }

  // From one colour
  const seed = ref((working.value.seed ?? working.value.schemes.light!.primary!).toLowerCase())
  const seedText = ref(seed.value.toUpperCase())
  const seedError = ref<string | undefined>()
  watch(seed, value => {
    seedText.value = value.toUpperCase()
  })
  watch(seedText, value => {
    if (/^#[0-9a-f]{6}$/i.test(value)) {
      seed.value = value.toLowerCase()
      seedError.value = undefined
    }
  })

  async function generate (): Promise<void> {
    if (!/^#[0-9a-f]{6}$/i.test(seedText.value)) {
      seedError.value = 'Enter a colour like #0A6780'
      return
    }
    generating.value = true
    try {
      // Loaded on demand: the colour maths stays out of the app's first download
      const { generateMaterialTheme } = await import('@/app/theme/materialGenerate')
      edit(generateMaterialTheme(seed.value, `From ${seed.value.toUpperCase()}`))
    } finally {
      generating.value = false
    }
  }

  // Colour by colour
  const MAIN_ROLES: readonly Role[] = [
    'primary', 'onPrimary', 'primaryContainer', 'onPrimaryContainer', 'secondary', 'tertiary',
    'error', 'onErrorContainer', 'background', 'surfaceContainerLowest', 'surfaceContainerLow',
    'surfaceContainer', 'surfaceContainerHigh', 'surfaceContainerHighest', 'onSurface',
    'onSurfaceVariant', 'outline', 'outlineVariant', 'inverseSurface',
  ]
  const allRoles = ref(false)
  const shownRoles = computed<readonly Role[]>(() => allRoles.value ? ROLES : MAIN_ROLES)

  function roleLabel (role: Role): string {
    const words = role.replace(/([A-Z])/g, ' $1').toLowerCase()
    return words.charAt(0).toUpperCase() + words.slice(1)
  }

  /** Where the app uses a colour (material.ts materialColors), so an admin knows what changes. */
  function roleUse (scheme: SchemeName, role: Role): string | null {
    const dark = scheme === 'dark'
    const uses: Partial<Record<Role, string>> = {
      primary: 'Buttons, links, focus rings',
      onPrimary: 'Text on primary buttons',
      primaryContainer: 'Information banners',
      onPrimaryContainer: 'Text in information banners',
      error: 'Errors and destructive buttons',
      errorContainer: 'Error banners',
      onErrorContainer: 'Error text',
      background: 'Behind the public pages',
      surfaceContainerLowest: dark ? 'Ground behind the tiles' : 'Tiles',
      surfaceContainerLow: dark ? 'Tiles' : 'Light fills',
      surfaceContainer: dark ? 'Light fills' : 'Ground behind the tiles, hover',
      surfaceContainerHigh: dark ? 'Hover' : 'Subtle fills',
      surfaceContainerHighest: 'Borders and dividers',
      onSurface: 'Main text',
      onSurfaceVariant: 'Secondary text',
      outline: 'Field borders',
      outlineVariant: 'Strong dividers',
      inverseSurface: 'Snackbars',
    }
    return uses[role] ?? null
  }

  function setRole (scheme: SchemeName, role: Role, value: string): void {
    const base = working.value
    edit({
      ...base,
      name: base.name === 'Built-in' ? 'Custom colours' : base.name,
      schemes: { ...base.schemes, [scheme]: { ...base.schemes[scheme], [role]: value.toUpperCase() } },
    })
  }

  // JSON
  const jsonText = ref(toExportJson(working.value))
  const jsonError = ref<string | null>(null)
  watch(working, value => {
    jsonText.value = toExportJson(value)
    jsonError.value = null
  })

  function readTheme (text: string, fallbackName?: string): MaterialTheme | string {
    let value: unknown
    try {
      value = JSON.parse(text)
    } catch {
      return 'This isn’t valid JSON. Check for a missing comma or quote.'
    }
    const parsed = parseMaterialTheme(value, fallbackName)
    return parsed.ok ? parsed.theme : parsed.error
  }

  function applyJson (): void {
    const result = readTheme(jsonText.value, working.value.name ?? undefined)
    if (typeof result === 'string') {
      jsonError.value = result
      return
    }
    edit(result)
  }

  // Upload and download
  async function upload (event: Event): Promise<void> {
    const input = event.target as HTMLInputElement
    const file = input.files?.[0]
    input.value = '' // the same file can be chosen again
    if (!file) {
      return
    }
    if (file.size > 512 * 1024) {
      fileError.value = 'That file is too big for a theme. Export it again from Material Theme Builder.'
      return
    }
    const result = readTheme(await file.text(), file.name.replace(/\.json$/i, ''))
    if (typeof result === 'string') {
      fileError.value = `We couldn’t use ${file.name}. ${result}`
      return
    }
    edit(result)
  }

  function download (): void {
    const blob = new Blob([toExportJson(working.value)], { type: 'application/json' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `${(working.value.name ?? 'brand-colours').replace(/[^\w.-]+/g, '-').toLowerCase()}.json`
    link.click()
    setTimeout(() => URL.revokeObjectURL(link.href), 1000)
  }

  // --- Save -------------------------------------------------------------------------------------

  async function save (): Promise<void> {
    if (!draft.value || saving.value) {
      return
    }
    saving.value = true
    saveError.value = null
    try {
      await branding.save(toBuiltIn.value ? null : draft.value)
      draft.value = null
      toBuiltIn.value = false
      toast.text = 'Saved. Everyone sees the new colours the next time their app opens or comes back to the front.'
      toast.show = true
    } catch (error) {
      if (error instanceof NetworkError) {
        saveError.value = 'This needs a connection. Your changes are still here; save again when you have signal.'
      } else if (error instanceof ApiError && error.status === 409) {
        await branding.refresh()
        saveError.value = 'Another admin changed the colours a moment ago. Yours are still here: save again to replace theirs, or discard to see them.'
      } else if (error instanceof ApiError) {
        saveError.value = error.detail
      } else {
        saveError.value = 'Something went wrong on our side. Try again in a minute.'
      }
    } finally {
      saving.value = false
    }
  }

  // --- Leaving with unsaved changes -----------------------------------------------------------------

  const { askLeave, confirmLeave, leave } = useLeaveGuard(dirty)

  function beforeUnload (event: BeforeUnloadEvent): void {
    if (dirty.value) {
      event.preventDefault()
    }
  }

  onBeforeRouteLeave(confirmLeave)
  onBeforeRouteUpdate(confirmLeave)
  onMounted(() => window.addEventListener('beforeunload', beforeUnload))
  onBeforeUnmount(() => {
    window.removeEventListener('beforeunload', beforeUnload)
    if (dirty.value) {
      branding.endPreview()
    }
  })
</script>
