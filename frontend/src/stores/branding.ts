import type { MaterialTheme } from '@/app/theme/material'
import type { ThemeInstance } from 'vuetify'
import { defineStore } from 'pinia'
import { computed, ref, shallowRef } from 'vue'
import { brandingApi } from '@/api/auth'
import { buildThemes, builtInMaterial } from '@/app/theme/brand'
import { BRANDING_STORAGE_KEY, readCachedBranding, writeCachedBranding } from '@/app/theme/brandingCache'

// Look again when the app comes back to the front, at most this often
const RECHECK_MS = 5 * 60 * 1000

/*
  The organization's brand colours (decision W4-12). Everyone gets them from the public
  GET /api/v1/auth/branding at start and when the app comes back to the front; the last answer is
  kept on the device (brandingCache.ts) so they apply offline and on the first paint.
  An admin can preview a theme on their own screen before saving it for everyone.
*/
export const useBrandingStore = defineStore('branding', () => {
  const saved = shallowRef(readCachedBranding())
  /** A theme being tried on this screen only; undefined when nothing is being previewed. */
  const preview = shallowRef<MaterialTheme | null | undefined>(undefined)
  const checkedAt = ref(0)
  let vuetify: ThemeInstance | null = null

  /** What the app shows now: the preview, else the saved theme, else the built-in one. */
  const active = computed<MaterialTheme>(() => {
    const chosen = preview.value === undefined ? saved.value.material : preview.value
    return chosen ?? builtInMaterial
  })
  const isCustom = computed(() => saved.value.material !== null)

  function apply (): void {
    if (!vuetify) {
      return
    }
    const themes = buildThemes(active.value)
    Object.assign(vuetify.themes.value.light!.colors, themes.light.colors)
    Object.assign(vuetify.themes.value.dark!.colors, themes.dark.colors)
    // The browser's title bar on phones follows the brand too
    setThemeColor('light', String(themes.light.colors!.primary))
    setThemeColor('dark', String(themes.dark.colors!.ground))
  }

  function adoptSaved (material: MaterialTheme | null, version: number): void {
    saved.value = { material, version }
    writeCachedBranding(saved.value)
    apply()
  }

  async function refresh (): Promise<void> {
    checkedAt.value = Date.now()
    try {
      const answer = await brandingApi.get()
      if (answer.version !== saved.value.version) {
        adoptSaved(answer.material, answer.version)
      }
    } catch {
      // Offline or the server is busy: keep the colours this device has
    }
  }

  function init (theme: ThemeInstance): void {
    vuetify = theme
    apply()
    void refresh()
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible' && Date.now() - checkedAt.value > RECHECK_MS) {
        void refresh()
      }
    })
    // Another tab on this device saved or fetched newer colours
    window.addEventListener('storage', event => {
      if (event.key === BRANDING_STORAGE_KEY) {
        saved.value = readCachedBranding()
        apply()
      }
    })
  }

  function startPreview (material: MaterialTheme | null): void {
    preview.value = material
    apply()
  }

  function endPreview (): void {
    preview.value = undefined
    apply()
  }

  /** Saves for everyone; `null` goes back to the built-in colours. Throws ApiError (409 if stale). */
  async function save (material: MaterialTheme | null): Promise<void> {
    const answer = await brandingApi.save({ material, version: saved.value.version })
    preview.value = undefined
    adoptSaved(answer.material, answer.version)
  }

  return { saved, preview, active, isCustom, init, refresh, startPreview, endPreview, save }
})

function setThemeColor (scheme: 'light' | 'dark', color: string): void {
  const meta = document.querySelector<HTMLMetaElement>(`meta[name="theme-color"][media*="${CSS.escape(scheme)}"]`)
  meta?.setAttribute('content', color)
}
