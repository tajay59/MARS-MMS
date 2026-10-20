import type { StationStatus, StationSummary } from '@/api/models'
import { lookOf, STATUSES } from '@/features/stations/stations'

/*
  The map (PRD MAP-1 to MAP-3; DBD "Map"). Marker and cluster pictures are strings here and the
  Leaflet code in MapView.vue only places them, so Vitest covers everything that is not Leaflet.

  Colours come from the status tokens through Tailwind classes (`text-station-*`), so they follow
  the theme; the shape tells the statuses apart without colour (DBD): circle, triangle, square
  with a cross, ring.
*/

export interface Positioned extends StationSummary {
  latitude: number
  longitude: number
}

export function hasPosition (station: StationSummary): station is Positioned {
  return typeof station.latitude === 'number' && typeof station.longitude === 'number'
    && Number.isFinite(station.latitude) && Number.isFinite(station.longitude)
}

/** Marker sizes in px: a selected station grows from 28 to 36 (DBD). */
export const MARKER_SIZE = 28
export const MARKER_SIZE_SELECTED = 36

const SHAPES: Record<StationStatus, string> = {
  operational: '<circle cx="14" cy="14" r="11" fill="currentColor" stroke="#fff" stroke-width="2"/>',
  degraded: '<path d="M14 3L26 24H2L14 3z" fill="currentColor" stroke="#fff" stroke-width="2" stroke-linejoin="round"/>',
  offline: '<rect x="3" y="3" width="22" height="22" rx="2" fill="currentColor" stroke="#fff" stroke-width="2"/><path d="M9.5 9.5l9 9M18.5 9.5l-9 9" stroke="#fff" stroke-width="2.4" stroke-linecap="round"/>',
  decommissioned: '<circle cx="14" cy="14" r="10" fill="#fff" stroke="currentColor" stroke-width="3"/>',
}

/** The marker's SVG. Only fixed strings go in, never a station's own text. */
export function markerSvg (status: string, size: number = MARKER_SIZE): string {
  const key = (STATUSES as readonly string[]).includes(status) ? status as StationStatus : 'decommissioned'
  return `<svg aria-hidden="true" class="${lookOf(key).mark}" focusable="false" height="${size}" viewBox="0 0 28 28" width="${size}">${SHAPES[key]}</svg>`
}

/** A cluster is a plain brand circle with a count (the legend says "several stations: zoom in"). */
export function clusterSize (count: number): number {
  if (count >= 100) {
    return 52
  }
  if (count >= 10) {
    return 46
  }
  return count >= 5 ? 40 : 34
}

/** The marker's name for screen readers and its tooltip: `Kingston Harbour, JM-KIN-001, Offline`. */
export function markerLabel (station: StationSummary): string {
  return `${station.name}, ${station.code}, ${lookOf(station.status).label}`
}

/** The bounds of the stations, padded in `fitBounds`; null for none. */
export function boundsOf (stations: readonly Positioned[]): [[number, number], [number, number]] | null {
  if (stations.length === 0) {
    return null
  }
  let south = 90
  let north = -90
  let west = 180
  let east = -180
  for (const s of stations) {
    south = Math.min(south, s.latitude)
    north = Math.max(north, s.latitude)
    west = Math.min(west, s.longitude)
    east = Math.max(east, s.longitude)
  }
  return [[south, west], [north, east]]
}

/** The view when no station has a position: the Caribbean, the area the basemap file covers. */
export const DEFAULT_VIEW = { center: [18.5, -73] as [number, number], zoom: 5 }
