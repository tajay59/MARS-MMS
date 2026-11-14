import type { Capture } from './store'
import type { BoardElement, BoardElementIn, BoardElementList, BoardElementPut, BoardMediaPatch, VisitOut } from '@/api/models'
import { boardApi, visitsApi } from '@/api/operations'
import { storageReport } from '@/offline/storage'
import { useSessionStore } from '@/stores/session'
import { refusal } from './localVisit'
import * as local from './store'
import { requestSync } from './syncApp'

/*
  Where the board and the visit's moves go (W14-6). A visit that is prepared on this phone by this
  person is read from and written to Dexie first, with its ops queued for the runner; any other
  visit goes straight to the server as before. The screens use these two objects wherever they
  used `boardApi` and `visitsApi`, and so need not know which it is.
*/

async function context (visitId: string) {
  let user
  try {
    user = useSessionStore().user
  } catch {
    return null // no app around (a unit test): everything goes to the server
  }
  if (!user) {
    return null
  }
  return local.contextFor(visitId, {
    id: user.id, name: user.name, admin: user.roles.includes('admin'),
  })
}

/** Run a change on the phone's copy, then ask for a sync: the answer is what the phone now holds. */
const MB = 1024 * 1024

/** The phone must have room for the file and some to spare, or nothing is half-stored (W14-9). */
async function ensureRoom (bytes: number): Promise<void> {
  const report = await storageReport().catch(() => null)
  if (report && report.quota > 0 && report.free < (bytes * 1.1) + (20 * MB)) {
    throw refusal('no_space', `Not enough space. This phone has ${Math.round(report.free / MB)} MB free and this needs ${Math.ceil(bytes / MB)} MB. Free some space, then add it again.`, 507)
  }
}

async function written<T> (ctx: Awaited<ReturnType<typeof context>>, run: (c: NonNullable<typeof ctx>) => Promise<T>): Promise<T> {
  const out = await run(ctx!)
  requestSync()
  return out
}

/** Whether this visit is kept on the phone (the sheet and the upload queue ask). */
export async function isLocal (visitId: string): Promise<boolean> {
  return (await context(visitId)) !== null
}

/** Keep a photo, video or file on the phone and queue it for the element (the visit must be local). */
export async function captureFile (
  visitId: string, stationId: string, elementId: string, section: string, capture: Capture,
): Promise<BoardElement> {
  const ctx = await context(visitId)
  if (!ctx) {
    throw new Error('This visit is not kept on this phone')
  }
  await ensureRoom(capture.file.size)
  return written(ctx, c => local.captureMedia(c, stationId, elementId, section, capture))
}

export const board = {
  async list (visitId: string, stationId: string, signal?: AbortSignal): Promise<BoardElementList> {
    const ctx = await context(visitId)
    return ctx ? local.listElements(ctx, stationId) : boardApi.list(visitId, stationId, signal)
  },

  async create (visitId: string, stationId: string, body: BoardElementIn): Promise<BoardElement> {
    const ctx = await context(visitId)
    return ctx ? written(ctx, c => local.createElement(c, stationId, body)) : boardApi.create(visitId, stationId, body)
  },

  async save (visitId: string, stationId: string, elementId: string, body: BoardElementPut): Promise<BoardElement> {
    const ctx = await context(visitId)
    return ctx ? written(ctx, c => local.saveElement(c, stationId, elementId, body)) : boardApi.save(visitId, stationId, elementId, body)
  },

  async remove (visitId: string, stationId: string, elementId: string, baseVersion: number): Promise<void> {
    const ctx = await context(visitId)
    if (ctx) {
      await written(ctx, c => local.removeElement(c, stationId, elementId, baseVersion))
      return
    }
    await boardApi.remove(visitId, stationId, elementId, baseVersion)
  },

  async changeMedia (visitId: string, stationId: string, elementId: string, mediaId: string, body: BoardMediaPatch): Promise<BoardElement> {
    const ctx = await context(visitId)
    if (ctx && body.caption !== undefined && body.hidden == null) {
      return written(ctx, c => local.changeCaption(c, stationId, elementId, mediaId, body.caption ?? null))
    }
    // Hiding from the client, or a caption on a file the server holds, needs the server
    return boardApi.changeMedia(visitId, stationId, elementId, mediaId, body)
  },

  async removeMedia (visitId: string, stationId: string, elementId: string, mediaId: string): Promise<BoardElement> {
    const ctx = await context(visitId)
    return ctx ? written(ctx, c => local.removeMedia(c, stationId, elementId, mediaId)) : boardApi.removeMedia(visitId, stationId, elementId, mediaId)
  },

  // Online only: a version needs the element and its files on the server
  addMedia: boardApi.addMedia,
  saveConfigVersion: boardApi.saveConfigVersion,
  requestFrom: boardApi.requestFrom,
}

export const visitGate = {
  async get (visitId: string, signal?: AbortSignal): Promise<VisitOut> {
    const ctx = await context(visitId)
    return ctx ? local.visitView(ctx) : visitsApi.get(visitId, signal)
  },

  async start (visitId: string): Promise<VisitOut> {
    const ctx = await context(visitId)
    return ctx ? written(ctx, c => local.startVisit(c)) : visitsApi.start(visitId)
  },

  async arrive (visitId: string, stationId: string): Promise<VisitOut> {
    const ctx = await context(visitId)
    return ctx ? written(ctx, c => local.arriveAt(c, stationId)) : visitsApi.arrive(visitId, stationId)
  },

  async depart (visitId: string, stationId: string): Promise<VisitOut> {
    const ctx = await context(visitId)
    return ctx ? written(ctx, c => local.departFrom(c, stationId)) : visitsApi.depart(visitId, stationId)
  },

  async end (visitId: string, body: { additional_visit_required: boolean, follow_up_notes?: string | null }): Promise<VisitOut> {
    const ctx = await context(visitId)
    return ctx
      ? written(ctx, c => local.endVisit(c, body))
      : visitsApi.end(visitId, { additional_visit_required: body.additional_visit_required, follow_up_notes: body.follow_up_notes ?? null })
  },
}
