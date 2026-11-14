import type { Ref } from 'vue'
import { reactive, watch } from 'vue'
import { mediaDetail } from '../../mediaLinks'

/*
  Thumbnails for the photos of the report, from the media service's ten-minute links (W11-10),
  a few at a time. Kept in memory only: the editor needs a connection (OFF-10) and a link acts as
  a password, so nothing is stored. A photo whose link cannot be had shows a plain box.
*/

const AT_ONCE = 6

export function useThumbs (ids: Ref<string[]>) {
  const thumbs = reactive<Record<string, string | undefined>>({})
  const asked = new Set<string>()

  async function fetchAll (list: string[]): Promise<void> {
    const wanted = list.filter(id => !asked.has(id))
    for (const id of wanted) {
      asked.add(id)
    }
    for (let from = 0; from < wanted.length; from += AT_ONCE) {
      await Promise.allSettled(wanted.slice(from, from + AT_ONCE).map(async id => {
        try {
          thumbs[id] = (await mediaDetail(id)).urls?.thumbnail ?? undefined
        } catch {
          // A box instead of a picture; the report prints either way
        }
      }))
    }
  }

  watch(ids, list => void fetchAll(list), { immediate: true })

  return thumbs
}
