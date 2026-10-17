import type { MaterialTheme } from './material'
import { parseMaterialTheme } from './material'

/*
  The organization's brand colours as last fetched, kept on the device (decision W4-12), so the
  app paints in them before the network answers and when there is none (OFF-10: the field shell
  works offline). This is not an API cache: the service worker never stores the response
  (TRD §13.3); the app keeps its own copy, read synchronously before Vuetify starts.
  It holds no personal data, so logout leaves it in place.
*/

export const BRANDING_STORAGE_KEY = 'mms-branding'

export interface CachedBranding {
  /** null: the built-in colours. */
  material: MaterialTheme | null
  /** The server's version; 0 until an admin first saves. */
  version: number
}

export function readCachedBranding (): CachedBranding {
  try {
    const raw = localStorage.getItem(BRANDING_STORAGE_KEY)
    if (!raw) {
      return { material: null, version: 0 }
    }
    const value = JSON.parse(raw) as { material?: unknown, version?: unknown }
    const version = typeof value.version === 'number' ? value.version : 0
    if (value.material === null || value.material === undefined) {
      return { material: null, version }
    }
    // Checked again: anything stored by an older app or edited by hand falls back to built-in
    const parsed = parseMaterialTheme(value.material)
    return parsed.ok ? { material: parsed.theme, version } : { material: null, version: 0 }
  } catch {
    return { material: null, version: 0 }
  }
}

export function writeCachedBranding (value: CachedBranding): void {
  try {
    localStorage.setItem(BRANDING_STORAGE_KEY, JSON.stringify(value))
  } catch {
    // Storage blocked or full: the colours still apply until the app closes
  }
}
