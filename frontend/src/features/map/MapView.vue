<template>
  <div class="relative size-full min-h-96 overflow-hidden bg-surface-100">
    <div
      ref="el"
      aria-label="Map of stations. Each station is a button; press Enter to see its details."
      class="absolute inset-0"
      role="application"
    />

    <div v-if="stations.length === 0" class="pointer-events-none absolute inset-0 grid place-items-center p-6 text-center">
      <p class="m-0 max-w-72 rounded-card bg-surface px-4 py-3 text-sm text-surface-700 shadow-md">{{ emptyText }}</p>
    </div>

    <!-- The legend repeats in words what each shape shows (DBD) -->
    <div class="pointer-events-none absolute bottom-7 left-2.5 z-[500] flex flex-col gap-1.5 rounded-card bg-surface px-2.5 py-2 text-xs text-surface-900 shadow-md">
      <span v-for="status in STATUSES" :key="status" class="flex items-center gap-2">
        <StationStatusMark :status="status" />{{ statusLook[status].label }}
      </span>

      <span class="flex items-center gap-2 border-t border-surface-200 pt-1.5 text-surface-600">
        <span class="inline-block size-2.5 shrink-0 rounded-full bg-primary" />Several stations: zoom in
      </span>
    </div>
  </div>
</template>

<script lang="ts" setup>
  import type { Positioned } from './map'
  import type { StationSummary } from '@/api/models'
  import type * as L from 'leaflet'
  import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
  import { useTheme } from 'vuetify'
  import StationStatusMark from '@/components/StationStatusMark.vue'
  import { dueLabel, dueState, lookOf, STATUSES, statusLook } from '@/features/stations/stations'
  import {
    boundsOf,
    clusterSize,
    DEFAULT_VIEW,
    MARKER_SIZE,
    MARKER_SIZE_SELECTED,
    markerLabel,
    markerSvg,
  } from './map'
  import { CachedRangeSource, TILE_MAX_ZOOM, TILES_DATA_ZOOM, TILES_URL } from './tiles'

  /*
    The Leaflet map (MAP-1, MAP-2). Markers are the status shapes from map.ts, clustered into plain
    brand circles with a count. Leaflet draws into its own DOM, so station text only ever goes in
    with textContent, never as HTML. The basemap is our own Protomaps file, drawn by protomaps-leaflet
    and kept range by range in Cache Storage as it is looked at (tiles.ts; F1, W7-9).
  */
  const props = defineProps<{
    stations: Positioned[]
    /** Changes when the filters do: the map then fits the stations that remain. */
    fitKey: string
    emptyText: string
  }>()
  const emit = defineEmits<{ open: [id: string] }>()

  const el = ref<HTMLElement | null>(null)
  // Leaflet and its plugin are loaded when the map first shows (a dynamic import), so the other
  // pages, and the first install, don't carry them
  let lf: typeof L
  let unmounted = false
  let map: L.Map | null = null
  let cluster: L.MarkerClusterGroup | null = null
  let basemap: L.Layer | null = null
  let makeBasemap: ((flavor: 'light' | 'dark') => L.Layer) | null = null
  const theme = useTheme()
  const markers = new Map<string, L.Marker>()
  let selected: string | null = null

  function iconFor (station: StationSummary, big: boolean): L.DivIcon {
    const size = big ? MARKER_SIZE_SELECTED : MARKER_SIZE
    return lf.divIcon({
      className: 'bg-transparent', // no Leaflet default white square
      html: markerSvg(station.status, size),
      iconSize: [size, size],
      iconAnchor: [size / 2, size / 2],
      popupAnchor: [0, -size / 2],
    })
  }

  function popupFor (station: StationSummary): HTMLElement {
    const root = document.createElement('div')
    root.className = 'flex w-52 flex-col gap-1.5'

    const name = document.createElement('strong')
    name.className = 'text-sm font-semibold text-surface-900'
    name.textContent = station.name

    const meta = document.createElement('div')
    meta.className = 'flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-surface-600'
    const code = document.createElement('span')
    code.className = 'font-mono font-medium text-surface-900'
    code.textContent = station.code
    const status = document.createElement('span')
    status.className = `inline-flex h-6 items-center rounded-full px-2 font-medium ${lookOf(station.status).chip}`
    status.textContent = lookOf(station.status).label
    meta.append(code, status)

    root.append(name, meta)

    const due = dueState(station.next_calibration_due_at)
    if (due) {
      const line = document.createElement('span')
      line.className = 'text-xs text-surface-600'
      line.textContent = `Calibration: ${dueLabel(due, station.next_calibration_due_at, station.time_zone)}`
      root.append(line)
    }

    const link = document.createElement('a')
    link.className = 'mt-0.5 text-sm font-medium text-primary no-underline hover:underline'
    link.href = `/stations/${encodeURIComponent(station.id)}`
    link.textContent = 'Open station'
    link.addEventListener('click', event => {
      // A plain click moves within the app; a modified one (new tab) is left to the browser
      if (!event.metaKey && !event.ctrlKey && !event.shiftKey && event.button === 0) {
        event.preventDefault()
        emit('open', station.id)
      }
    })
    root.append(link)
    return root
  }

  function select (id: string | null): void {
    if (selected && selected !== id) {
      const before = markers.get(selected)
      const station = props.stations.find(s => s.id === selected)
      if (before && station) {
        before.setIcon(iconFor(station, false))
      }
    }
    selected = id
    const marker = id ? markers.get(id) : undefined
    const station = props.stations.find(s => s.id === id)
    if (marker && station) {
      marker.setIcon(iconFor(station, true))
    }
  }

  function draw (): void {
    if (!cluster) {
      return
    }
    cluster.clearLayers()
    markers.clear()
    selected = null
    const layers: L.Marker[] = []
    for (const station of props.stations) {
      const marker = lf.marker([station.latitude, station.longitude], {
        icon: iconFor(station, false),
        title: markerLabel(station),
        alt: markerLabel(station),
        keyboard: true,
        riseOnHover: true,
      })
      marker.on('add', () => marker.getElement()?.setAttribute('aria-label', markerLabel(station)))
      marker.bindPopup(() => popupFor(station), { closeButton: true, minWidth: 208, autoPanPadding: [24, 24] })
      marker.on('popupopen', () => select(station.id))
      marker.on('popupclose', () => select(null))
      markers.set(station.id, marker)
      layers.push(marker)
    }
    cluster.addLayers(layers)
  }

  function fit (): void {
    const bounds = boundsOf(props.stations)
    if (!map) {
      return
    }
    if (!bounds) {
      map.setView(DEFAULT_VIEW.center, DEFAULT_VIEW.zoom)
      return
    }
    map.fitBounds(bounds, { padding: [48, 48], maxZoom: 12, animate: false })
  }

  onMounted(async () => {
    const [leaflet] = await Promise.all([
      import('leaflet'),
      import('leaflet/dist/leaflet.css'),
      import('leaflet.markercluster/dist/MarkerCluster.css'),
    ])
    lf = (leaflet as unknown as { default?: typeof L }).default ?? leaflet
    // markercluster adds itself to the global `L` while it loads
    ;(globalThis as { L?: typeof L }).L = lf
    await import('leaflet.markercluster')
    if (!el.value || unmounted) {
      return
    }
    // eslint-disable-next-line unicorn/no-array-callback-reference, unicorn/no-array-method-this-argument -- Leaflet's map is not Array#map
    map = lf.map(el.value, { zoomControl: false, attributionControl: true, worldCopyJump: true })
    lf.control.zoom({ position: 'topright', zoomInTitle: 'Zoom in', zoomOutTitle: 'Zoom out' }).addTo(map)
    const { PMTiles } = await import('pmtiles')
    const { leafletLayer } = await import('protomaps-leaflet')
    if (!el.value || unmounted) {
      return
    }
    const source = new CachedRangeSource(TILES_URL)
    void source.prune()
    const archive = new PMTiles(source)
    makeBasemap = flavor => leafletLayer({
      url: archive,
      flavor,
      maxZoom: TILE_MAX_ZOOM,
      maxDataZoom: TILES_DATA_ZOOM,
      lang: 'en',
    }) as unknown as L.Layer
    showBasemap()

    cluster = lf.markerClusterGroup({
      showCoverageOnHover: false,
      maxClusterRadius: 50,
      spiderfyOnMaxZoom: true,
      iconCreateFunction: group => {
        const count = group.getChildCount()
        const size = clusterSize(count)
        const label = document.createElement('div')
        label.className = 'grid size-full place-items-center rounded-full border-2 border-white bg-primary text-sm font-semibold tabular-nums text-on-primary shadow-md'
        label.textContent = String(count)
        return lf.divIcon({ html: label, className: 'bg-transparent', iconSize: [size, size] })
      },
    })
    map.addLayer(cluster)
    draw()
    fit()
  })

  /** The basemap in the theme's colours: light or dark flavor, swapped when the theme changes. */
  function showBasemap (): void {
    if (!map || !makeBasemap) {
      return
    }
    basemap?.remove()
    basemap = makeBasemap(theme.global.name.value === 'dark' ? 'dark' : 'light').addTo(map)
  }

  watch(() => theme.global.name.value, () => showBasemap())
  watch(() => props.stations, () => {
    draw()
  })
  watch(() => props.fitKey, () => fit())

  onBeforeUnmount(() => {
    unmounted = true
    map?.remove()
    map = null
    cluster = null
    basemap = null
    markers.clear()
  })
</script>

<style>
  /* Leaflet draws outside Vue and Tailwind: a few rules that cannot be classes */
  .leaflet-container {
    font-family: inherit;
    background: transparent;
  }

  .leaflet-popup-content-wrapper,
  .leaflet-popup-tip {
    background: rgb(var(--v-theme-surface));
    color: rgb(var(--v-theme-on-surface));
  }

  .leaflet-popup-content {
    margin: 12px 14px;
  }

  .leaflet-bar a {
    background-color: rgb(var(--v-theme-surface));
    color: rgb(var(--v-theme-on-surface));
    border-color: rgb(var(--v-theme-surface-200));
  }

  .leaflet-container a.leaflet-popup-close-button {
    width: 32px;
    height: 32px;
    font-size: 20px;
    line-height: 32px;
  }

  .leaflet-control-attribution {
    background: rgba(var(--v-theme-surface), 0.85);
    color: rgb(var(--v-theme-on-surface));
  }

  .leaflet-control-attribution a {
    color: rgb(var(--v-theme-primary));
  }

  .leaflet-marker-icon:focus-visible {
    outline: 2px solid rgb(var(--v-theme-primary));
    outline-offset: 2px;
    border-radius: 50%;
  }
</style>
