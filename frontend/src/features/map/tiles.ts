import type { RangeResponse, Source } from 'pmtiles'
import { TILE_CACHE } from '@/app/pwa/runtimeCaches'

/*
  The map's tiles (finding F1, decision W7-9). The basemap is one PMTiles file on our own host, a
  Protomaps extract of the Caribbean (infra/scripts/extract-tiles.sh), so the OpenStreetMap tile
  servers are never asked and their "no offline use" rule does not apply. The library reads the
  file in byte ranges; this source keeps each range it read in Cache Storage, so a map that was
  looked at once can be looked at again with no signal. The page does the caching, not the service
  worker, so the worker still caches nothing but the app shell (TRD §7.6).

  A file name is never reused for different content: a new extract gets a new name (and so new
  cache keys), because ranges are cached by offset.
*/

/** The extract the app draws, served by the gateway from `/tiles/` (infra/nginx). */
export const TILES_URL = '/tiles/caribbean-20261019-z14.pmtiles'

/** The file's last zoom level; the vector tiles are drawn larger beyond it, up to `TILE_MAX_ZOOM`. */
export const TILES_DATA_ZOOM = 14
export const TILE_MAX_ZOOM = 17

/** Ranges kept at most; the oldest third goes when a map opens above this. */
export const MAX_CACHED_RANGES = 6000

export class CachedRangeSource implements Source {
  readonly url: string
  private readonly cacheName: string

  constructor (url: string, cacheName: string = TILE_CACHE) {
    this.url = new URL(url, globalThis.location?.href ?? 'http://localhost/').href
    this.cacheName = cacheName
  }

  getKey (): string {
    return this.url
  }

  async getBytes (offset: number, length: number, signal?: AbortSignal): Promise<RangeResponse> {
    const last = offset + length - 1
    const key = `${this.url}?bytes=${offset}-${last}`
    const cache = await this.open()

    const hit = await cache?.match(key).catch(() => undefined)
    if (hit) {
      return { data: await hit.arrayBuffer() }
    }

    const response = await fetch(this.url, { headers: { Range: `bytes=${offset}-${last}` }, signal })
    if (response.status !== 206) {
      // 200 would be the whole file from a server that ignores Range: never read that into memory
      throw new Error(`Tiles: expected a partial answer (206), got ${response.status}`)
    }
    const data = await response.arrayBuffer()
    if (data.byteLength !== length) {
      // A short answer cached under this key would be served again for ever
      throw new Error(`Tiles: asked for ${length} bytes, got ${data.byteLength}`)
    }
    try {
      await cache?.put(key, new Response(data.slice(0)))
    } catch {
      // Over quota or Cache Storage refused: the tile still draws
    }
    return {
      data,
      etag: response.headers.get('etag') ?? undefined,
      cacheControl: response.headers.get('cache-control') ?? undefined,
      expires: response.headers.get('expires') ?? undefined,
    }
  }

  /** Drops the oldest third of the kept ranges once there are more than `max`. */
  async prune (max: number = MAX_CACHED_RANGES): Promise<void> {
    const cache = await this.open()
    if (!cache) {
      return
    }
    try {
      const keys = await cache.keys()
      if (keys.length <= max) {
        return
      }
      await Promise.all(keys.slice(0, Math.ceil(keys.length / 3)).map(async request => cache.delete(request)))
    } catch {
      // Nothing to prune
    }
  }

  private async open (): Promise<Cache | null> {
    try {
      return (await globalThis.caches?.open(this.cacheName)) ?? null
    } catch {
      return null // no Cache Storage (a private window, an old browser): tiles just aren't kept
    }
  }
}
