import { gsap } from 'gsap'
import { CustomEase } from 'gsap/CustomEase'
import { ref } from 'vue'

/*
  Motion for the app shell (decision W4-10): GSAP tweens for tile widths, page and pane entrances,
  the rail's hover, indicator and tooltips. GSAP is bundled (no CDN, CSP script-src 'self') and
  writes inline styles through the CSSOM, which the CSP allows.

  DBD "Motion": hovers and tooltips ~150 ms, pages ~220 ms, ease-out, nothing loops. The pane's
  width uses Material 3's emphasized curve (400 ms opening, 300 ms closing): a short ease-in-out
  covered most of the distance in a frame or two and read as a jump.
  Everything is instant when the device asks for reduced motion (WCAG 2.3.3) or the person turns
  animations off in Settings (stored on this device).
*/

export const MOTION_STORAGE_KEY = 'mms-motion'
export type MotionPreference = 'system' | 'reduced'

export const DURATION = {
  hover: 0.15,
  tip: 0.15,
  page: 0.22,
  record: 0.45,
  tileOpen: 0.4,
  tileClose: 0.3,
} as const

gsap.registerPlugin(CustomEase)

// Material 3 "emphasized" (m3.material.io, Motion › Easing and duration): a gentle start, a quick
// middle and a long settle
CustomEase.create('emphasized', 'M0,0 C0.05,0 0.133333,0.06 0.166666,0.4 0.208333,0.82 0.25,1 1,1')
// ... and its decelerate form for things arriving: no slow start, a long, soft landing
CustomEase.create('emphasizedDecelerate', '0.05,0.7,0.1,1')

export const EASE = {
  out: 'power2.out',
  emphasized: 'emphasized',
  decelerate: 'emphasizedDecelerate',
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

/*
  Press feedback for list rows: shrink while held, then spring back past full size and settle.
  The shrink eases out (it answers the finger at once and slows into 96 %, 80 ms); the release (320 ms) is
  back.out(4), which overshoots by about 1 % before landing, so the row "grows" back.
*/
const PRESSED = 0.96

export function pressDown (el: Element | null): void {
  gsap.to(el, { scale: PRESSED, duration: dur(0.08), ease: 'power2.out', overwrite: true })
}

export function pressUp (el: Element | null): void {
  gsap.to(el, { scale: 1, duration: dur(0.32), ease: 'back.out(4)', overwrite: true, clearProps: 'transform' })
}

/** The same shrink and spring in one go, for a click from the keyboard (Enter or Space). */
export function pressPulse (el: Element | null): void {
  gsap.timeline({ defaults: { overwrite: true } })
    .to(el, { scale: PRESSED, duration: dur(0.07), ease: 'power2.out' })
    .to(el, { scale: 1, duration: dur(0.32), ease: 'back.out(4)', clearProps: 'transform' })
}

export { gsap } from 'gsap'
