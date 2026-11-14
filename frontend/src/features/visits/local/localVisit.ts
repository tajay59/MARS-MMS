import type { VisitOut, VisitStatus } from '@/api/models'
import { ApiError } from '@/api/problem'

/*
  A prepared visit as the phone sees it with no signal (W14-6; TRD §7.2). The bundle holds the
  visit as it was when it was prepared; what the person does on the phone (start, arrive, depart,
  end) is kept beside it as a small state and laid over it. The same rules as the server's
  (`domain/visits/lifecycle.py`, `actions.py`) decide what is allowed, well enough for the screen;
  the server stays the judge when the ops sync. No Vue, no Dexie: tests cover it directly.
*/

export interface Me {
  id: string
  name: string
  admin: boolean
}

export interface VisitState {
  status: VisitStatus
  started_at: string | null
  ended_at: string | null
  additional_visit_required: boolean | null
  follow_up_notes: string | null
  stations: Record<string, { arrived_at: string | null, departed_at: string | null }>
}

/** A refusal made on the phone, shaped like the server's so the screens say it the same way. */
export function refusal (code: string, detail: string, status = 409, extra: Record<string, unknown> = {}): ApiError {
  return new ApiError(status, { code, detail, title: detail, ...extra })
}

export function stateOf (visit: VisitOut): VisitState {
  return {
    status: visit.status,
    started_at: visit.started_at,
    ended_at: visit.ended_at,
    additional_visit_required: visit.additional_visit_required,
    follow_up_notes: visit.follow_up_notes,
    stations: Object.fromEntries(visit.stations.map(s => [s.station_id, {
      arrived_at: s.arrived_at, departed_at: s.departed_at,
    }])),
  }
}

export function attends (visit: VisitOut, me: Me): boolean {
  return me.admin || visit.staff.some(p => p.id === me.id)
}

function ownsStation (visit: VisitOut, stationId: string, me: Me): boolean {
  const station = visit.stations.find(s => s.station_id === stationId)
  if (!station) {
    throw refusal('not_found', 'That station is not on this visit', 404)
  }
  return me.admin || station.owner.id === me.id
}

function requireStarted (state: VisitState): void {
  if (state.status === 'cancelled') {
    throw refusal('visit_cancelled', 'This visit was cancelled')
  }
  if (state.status === 'ended') {
    throw refusal('already_ended', 'This visit has already ended')
  }
  if (state.status !== 'started') {
    throw refusal('not_started', 'Start the visit first')
  }
}

/** The visit with the phone's own moves laid over it, and what the person may do next. */
export function overlay (visit: VisitOut, state: VisitState, me: Me): VisitOut {
  const stations = visit.stations.map(s => {
    const own = state.stations[s.station_id] ?? { arrived_at: null, departed_at: null }
    const actions: ('arrive' | 'depart')[] = []
    if (state.status === 'started' && (me.admin || s.owner.id === me.id)) {
      if (own.arrived_at === null) {
        actions.push('arrive')
      } else if (own.departed_at === null) {
        actions.push('depart')
      }
    }
    return { ...s, arrived_at: own.arrived_at, departed_at: own.departed_at, actions }
  })
  const actions: VisitOut['actions'] = []
  if (attends(visit, me)) {
    if (state.status === 'planned') {
      actions.push('start')
    } else if (state.status === 'started') {
      actions.push('end')
    }
  }
  return {
    ...visit,
    status: state.status,
    started_at: state.started_at,
    ended_at: state.ended_at,
    additional_visit_required: state.additional_visit_required,
    follow_up_notes: state.follow_up_notes,
    stations,
    actions,
  }
}

export function start (visit: VisitOut, state: VisitState, me: Me, at: string): VisitState {
  if (!attends(visit, me)) {
    throw refusal('not_attending', 'Only the people attending can do this', 403)
  }
  if (state.status === 'started') {
    return state
  }
  if (state.status === 'cancelled') {
    throw refusal('visit_cancelled', 'This visit was cancelled')
  }
  if (state.status !== 'planned') {
    throw refusal('already_ended', 'This visit has already ended')
  }
  return { ...state, status: 'started', started_at: at }
}

function withStation (state: VisitState, stationId: string, change: Partial<VisitState['stations'][string]>): VisitState {
  const own = state.stations[stationId] ?? { arrived_at: null, departed_at: null }
  return { ...state, stations: { ...state.stations, [stationId]: { ...own, ...change } } }
}

export function arrive (visit: VisitOut, state: VisitState, me: Me, stationId: string, at: string): VisitState {
  if (!ownsStation(visit, stationId, me)) {
    throw refusal('not_owner', 'Only the station’s owner can do this', 403)
  }
  requireStarted(state)
  if (state.stations[stationId]?.arrived_at) {
    return state
  }
  return withStation(state, stationId, { arrived_at: at })
}

export function depart (visit: VisitOut, state: VisitState, me: Me, stationId: string, at: string): VisitState {
  if (!ownsStation(visit, stationId, me)) {
    throw refusal('not_owner', 'Only the station’s owner can do this', 403)
  }
  requireStarted(state)
  const own = state.stations[stationId]
  if (!own?.arrived_at) {
    throw refusal('not_arrived', 'Arrive at the station first')
  }
  if (own.departed_at) {
    return state
  }
  if (Date.parse(at) < Date.parse(own.arrived_at)) {
    throw refusal('bad_time', 'That is before the arrival', 422)
  }
  return withStation(state, stationId, { departed_at: at })
}

export function end (
  visit: VisitOut, state: VisitState, me: Me,
  body: { additional_visit_required: boolean, follow_up_notes?: string | null, at: string },
): VisitState {
  if (!attends(visit, me)) {
    throw refusal('not_attending', 'Only the people attending can do this', 403)
  }
  if (state.status === 'ended') {
    return state
  }
  requireStarted(state)
  const notes = (body.follow_up_notes ?? '').trim() || null
  if (body.additional_visit_required && !notes) {
    throw refusal('notes_required', 'Say what work remains', 422)
  }
  return {
    ...state,
    status: 'ended',
    ended_at: body.at,
    additional_visit_required: body.additional_visit_required,
    follow_up_notes: notes,
  }
}
