import type { RequestDetail } from '@/api/models'
import { requestsApi } from '@/api/operations'
import { ApiError, NetworkError } from '@/api/problem'

/*
  Claim and release (PRD REQ-7; AFD J5 step 2), with the errors turned into sentences. No Vue, so
  Vitest covers it. A lost race (two people claiming at once) says who has it; either way the page
  reloads what it shows (`reload`).
*/

export type StaffingResult
  = | { ok: true, detail: RequestDetail }
    | { ok: false, message: string, reload: boolean }

export function namesOf (value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : []
}

export function failureOf (error: unknown, verb: 'claim' | 'release' | 'assign'): StaffingResult & { ok: false } {
  if (error instanceof NetworkError) {
    return { ok: false, message: 'You’re offline. This needs a connection.', reload: false }
  }
  if (error instanceof ApiError && error.code === 'already_assigned') {
    const who = namesOf(error.body.claimed_by)
    return {
      ok: false,
      message: who.length > 0 ? `${who.join(' and ')} claimed it first.` : 'Someone else claimed it first.',
      reload: true,
    }
  }
  if (error instanceof ApiError && (error.code === 'request_changed' || error.code === 'bad_transition' || error.status === 409)) {
    return { ok: false, message: 'Someone else just changed this request. It has been reloaded.', reload: true }
  }
  if (error instanceof ApiError && error.status === 404) {
    return { ok: false, message: 'We can’t find this request any more.', reload: true }
  }
  return { ok: false, message: `We couldn’t ${verb} it. Try again in a moment.`, reload: false }
}

export async function claimRequest (id: string): Promise<StaffingResult> {
  try {
    return { ok: true, detail: await requestsApi.claim(id) }
  } catch (error) {
    return failureOf(error, 'claim')
  }
}

export async function releaseRequest (id: string): Promise<StaffingResult> {
  try {
    return { ok: true, detail: await requestsApi.release(id) }
  } catch (error) {
    return failureOf(error, 'release')
  }
}
