import { computed, reactive } from 'vue'

/*
  The install prompt (manifest-install.md; W13-12). Chrome and Edge fire `beforeinstallprompt` once,
  early, and want it kept until the person chooses; Safari on iPhone never fires it (the Prepare
  panel explains the Home Screen steps instead). "Not now" hides the offer for 14 days, and an
  installed app is never offered it.
*/

interface InstallEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

const HIDDEN_KEY = 'mms-install-hidden'
const HIDE_MS = 14 * 24 * 60 * 60 * 1000

const state = reactive<{ event: InstallEvent | null, installed: boolean, hiddenUntil: number }>({
  event: null,
  installed: false,
  hiddenUntil: readHidden(),
})

let listening = false

function readHidden (): number {
  try {
    return Number(localStorage.getItem(HIDDEN_KEY)) || 0
  } catch {
    return 0
  }
}

/** Starts listening; call it once, as early as the app starts (the event does not wait). */
export function captureInstallPrompt (): void {
  if (listening || typeof globalThis.addEventListener !== 'function') {
    return
  }
  listening = true
  globalThis.addEventListener('beforeinstallprompt', event => {
    event.preventDefault()
    state.event = event as InstallEvent
  })
  globalThis.addEventListener('appinstalled', () => {
    state.event = null
    state.installed = true
  })
}

/** The browser has an install prompt to show. */
export const canInstall = computed(() => state.event !== null && !state.installed)

/** …and the person has not just said "Not now". */
export const offerInstall = computed(() => canInstall.value && Date.now() >= state.hiddenUntil)

export async function promptInstall (): Promise<'accepted' | 'dismissed' | 'unavailable'> {
  const event = state.event
  if (!event) {
    return 'unavailable'
  }
  await event.prompt()
  const { outcome } = await event.userChoice
  // The browser allows one prompt per event
  state.event = null
  if (outcome === 'accepted') {
    state.installed = true
  }
  return outcome
}

export function hideInstallOffer (now: number = Date.now()): void {
  state.hiddenUntil = now + HIDE_MS
  try {
    localStorage.setItem(HIDDEN_KEY, String(state.hiddenUntil))
  } catch {
    // Private window: the offer comes back next time
  }
}

/** For tests. */
export function resetInstallForTests (): void {
  state.event = null
  state.installed = false
  state.hiddenUntil = 0
}

export function simulateInstallPrompt (event: InstallEvent): void {
  state.event = event
}
