import { gsap } from 'gsap'
import { ref } from 'vue'

/*
  Motion for the app shell (decision W4-10): GSAP tweens for tile widths, page and pane entrances,
  the rail's hover, indicator and tooltips. GSAP is bundled (no CDN, CSP script-src 'self') and
  writes inline styles through the CSSOM, which the CSP allows.

  DBD "Motion": hovers and tooltips ~150 ms, tiles and pages ~200-260 ms, ease-out, nothing loops.
  Everything is instant when the device asks for reduced motion (WCAG 2.3.3) or the person turns
  animations off in Settings (stored on this device).
*/

export const MOTION_STORAGE_KEY = 'mms-motion'
export type MotionPreference = 'system' | 'reduced'

export const DURATION = {
  hover: 0.15,
  tip: 0.15,
  page: 0.22,
  tile: 0.26,
} as const

export const EASE = {
  out: 'power2.out',
  inOut: 'power3.inOut',
  pop: 'back.out(2.5)',
} as const

const deviceQuery = typeof window === 'undefined' ? null : window.matchMedia('(prefers-reduced-motion: reduce)')

function readPreference (): MotionPreference {
  try {
    return localStorage.getItem(MOTION_STORAGE_KEY) === 'reduced' ? 'reduced' : 'system'
  } catch {
    return 'system'
  }
}

/** The person's choice on this device: follow the device, or always reduce. */
export const motionPreference = ref<MotionPreference>(readPreference())

function syncClass (): void {
  // base.css turns CSS transitions off under this class, as it does for the media query
  document.documentElement.classList.toggle('app-reduced-motion', motionPreference.value === 'reduced')
}

if (typeof document !== 'undefined') {
  syncClass()
}

export function setMotionPreference (value: MotionPreference): void {
  motionPreference.value = value
  try {
    localStorage.setItem(MOTION_STORAGE_KEY, value)
  } catch {
    // Storage blocked: the choice still applies until the app closes
  }
  syncClass()
}

export function reducedMotion (): boolean {
  return motionPreference.value === 'reduced' || Boolean(deviceQuery?.matches)
}

/** A duration in seconds, or 0 when motion is reduced. */
export function dur (seconds: number): number {
  return reducedMotion() ? 0 : seconds
}

gsap.defaults({ ease: EASE.out, overwrite: 'auto' })

export { gsap } from 'gsap'
