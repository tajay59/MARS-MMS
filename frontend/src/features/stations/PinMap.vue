<template>
  <div class="relative size-full min-h-72 overflow-hidden bg-surface-100">
    <div
      ref="el"
      aria-label="Map. Click or tap to put the station there; the latitude and longitude fields fill in. Typing them moves the pin."
      class="absolute inset-0"
      role="application"
    />

    <p class="pointer-events-none absolute bottom-7 left-2.5 z-[500] m-0 max-w-80 rounded-card bg-surface px-2.5 py-1.5 text-xs text-surface-700 shadow-md">
      Other stations are grey dots, so a pin too close to one is easy to see.
    </p>
  </div>
</template>

<script lang="ts" setup>
  import type * as L from 'leaflet'
  import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
  import { useTheme } from 'vuetify'
  import { DEFAULT_VIEW } from '@/features/map/map'
  import { CachedRangeSource, TILE_MAX_ZOOM, TILES_DATA_ZOOM, TILES_URL } from '@/features/map/tiles'

  /*
    The new-station and edit forms' map (approved "AWS-MMS Stations redesign"): a click puts the
    pin, the fields are the accessible way and stay the source of truth. Leaflet and the basemap
    load with import() when the form opens, as on the Map page, so they stay out of the app chunk
    and the precache.
  */
  const props = defineProps<{
    latitude: number | null
    longitude: number | null
    /** The other stations, drawn small and grey. */
    others: readonly { latitude: number, longitude: number, code: string }[]
    /** Where to look while there is no pin yet: the chosen country's stations. */
    focus?: readonly [number, number][]
  }>()
  const emit = defineEmits<{ pick: [latitude: number, longitude: number] }>()

  const el = ref<HTMLElement | null>(null)
  const theme = useTheme()
  let lf: typeof L
  let map: L.Map | null = null
  let pin: L.Marker | null = null
  let dots: L.LayerGroup | null = null
  let basemap: L.Layer | null = null
  let makeBasemap: ((flavor: 'light' | 'dark') => L.Layer) | null = null
  let unmounted = false

  const PIN_SVG = '<svg width="36" height="36" viewBox="0 0 24 24" aria-hidden="true"><path fill="rgb(var(--v-theme-primary))" stroke="white" stroke-width="1" d="M12,2A7,7 0 0,1 19,9C19,14.25 12,22 12,22C12,22 5,14.25 5,9A7,7 0 0,1 12,2M12,6.5A2.5,2.5 0 0,0 9.5,9A2.5,2.5 0 0,0 12,11.5A2.5,2.5 0 0,0 14.5,9A2.5,2.5 0 0,0 12,6.5Z"/></svg>'

  function round (n: number): number {
    return Math.round(n * 10_000) / 10_000
  }

  function placePin (): void {
    if (!map) {
      return
    }
    const { latitude: lat, longitude: lon } = props
    if (lat === null || lon === null) {
      pin?.remove()
      pin = null
      return
    }
    if (pin) {
      pin.setLatLng([lat, lon])
    } else {
      pin = lf.marker([lat, lon], {
        icon: lf.divIcon({ className: 'bg-transparent', html: PIN_SVG, iconSize: [36, 36], iconAnchor: [18, 34] }),
        keyboard: false,
        interactive: false,
      }).addTo(map)
    }
    if (!map.getBounds().contains([lat, lon])) {
      map.setView([lat, lon], Math.max(map.getZoom(), 9), { animate: false })
    }
  }

  /** Small dots when zoomed out, so a few hundred stations stay dots and not one grey blob. */
  function dotRadius (): number {
    const zoom = map?.getZoom() ?? 0
    if (zoom < 7) {
      return 2.5
    }
    return zoom < 10 ? 4 : 5
  }

  function drawOthers (): void {
    if (!map) {
      return
    }
    dots?.remove()
    dots = lf.layerGroup(props.others.map(s => lf.circleMarker([s.latitude, s.longitude], {
      radius: dotRadius(),
      color: 'white',
      weight: 1,
      fillColor: '#64748B',
      fillOpacity: 0.9,
      interactive: false,
    }))).addTo(map)
  }

  /** With no pin yet, look at the chosen country's stations (the closest a pin is likely to go). */
  function lookAtFocus (): void {
    const points = props.focus ?? []
    if (!map || points.length === 0 || (props.latitude !== null && props.longitude !== null)) {
      return
    }
    if (points.length === 1) {
      map.setView(points[0]!, 9, { animate: false })
    } else {
      map.fitBounds(lf.latLngBounds(points.map(([lat, lon]) => lf.latLng(lat, lon))), { padding: [32, 32], maxZoom: 10, animate: false })
    }
  }

  function showBasemap (): void {
    if (!map || !makeBasemap) {
      return
    }
    basemap?.remove()
    basemap = makeBasemap(theme.global.name.value === 'dark' ? 'dark' : 'light').addTo(map)
  }

  onMounted(async () => {
    const [leaflet] = await Promise.all([import('leaflet'), import('leaflet/dist/leaflet.css')])
    lf = (leaflet as unknown as { default?: typeof L }).default ?? leaflet
    if (!el.value || unmounted) {
      return
    }
    // eslint-disable-next-line unicorn/no-array-callback-reference, unicorn/no-array-method-this-argument -- Leaflet's map is not Array#map
    map = lf.map(el.value, { zoomControl: false, attributionControl: true, worldCopyJump: true })
    lf.control.zoom({ position: 'topright', zoomInTitle: 'Zoom in', zoomOutTitle: 'Zoom out' }).addTo(map)
    const start = props.latitude !== null && props.longitude !== null
      ? { center: [props.latitude, props.longitude] as [number, number], zoom: 10 }
      : DEFAULT_VIEW
    map.setView(start.center, start.zoom)
    map.on('click', event => emit('pick', round(event.latlng.lat), round(event.latlng.lng)))
    map.on('zoomend', () => {
      const radius = dotRadius()
      dots?.eachLayer(layer => (layer as L.CircleMarker).setRadius(radius))
    })

    const { PMTiles } = await import('pmtiles')
    const { leafletLayer } = await import('protomaps-leaflet')
    if (!map || unmounted) {
      return
    }
    const archive = new PMTiles(new CachedRangeSource(TILES_URL))
    makeBasemap = flavor => leafletLayer({ url: archive, flavor, maxZoom: TILE_MAX_ZOOM, maxDataZoom: TILES_DATA_ZOOM, lang: 'en' }) as unknown as L.Layer
    showBasemap()
    drawOthers()
    placePin()
    lookAtFocus()
  })

  watch(() => [props.latitude, props.longitude], () => placePin())
  watch(() => props.others, () => drawOthers())
  watch(() => props.focus, () => lookAtFocus())
  watch(() => theme.global.name.value, () => showBasemap())

  onBeforeUnmount(() => {
    unmounted = true
    map?.remove()
    map = null
    pin = null
    dots = null
  })
</script>
