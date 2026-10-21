import type { NotificationOut } from '@/api/models'
import type { SocketState } from '@/app/realtime/socket'
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { notificationsApi } from '@/api/notifications'
import { accessToken, onSessionChange, refreshSession } from '@/app/auth/session'
import { emitLive } from '@/app/realtime/bus'
import { browserSocket, RealtimeSocket } from '@/app/realtime/socket'
import { asEntityUpdate, isNotification, mergeNewest } from '@/features/notifications/notifications'

/*
  The person's notifications and the live channel behind them (PRD NOT-1, NOT-2, NOT-5). The list
  and the unread count live in memory only: the service worker never caches API answers and
  nothing about a person's notifications is written to the device (TRD §7.6), so after a reload or
  a long sleep the store asks again, and after a reconnect it asks for what came after the last
  one it has. Logging out empties it.
*/
export const useNotificationsStore = defineStore('notifications', () => {
  const items = ref<NotificationOut[]>([])
  const unread = ref(0)
  const loaded = ref(false)
  const loading = ref(false)
  const error = ref<'offline' | 'failed' | null>(null)
  const nextBefore = ref<string | null>(null)
  const live = ref<SocketState>('off')
  /** The newest notification that arrived live, for the toast; the page clears it. */
  const arrived = ref<NotificationOut | null>(null)

  let socket: RealtimeSocket | null = null
  let listening = false

  function adopt (page: { items: NotificationOut[], unread: number }): void {
    unread.value = page.unread
    items.value = mergeNewest(items.value, page.items)
  }

  async function load (): Promise<void> {
    loading.value = true
    try {
      const page = await notificationsApi.list({ limit: 50 })
      items.value = page.items
      unread.value = page.unread
      nextBefore.value = page.next_before
      loaded.value = true
      error.value = null
    } catch (error_) {
      error.value = error_ instanceof Error && error_.name === 'NetworkError' ? 'offline' : 'failed'
    } finally {
      loading.value = false
    }
  }

  async function loadMore (): Promise<void> {
    if (!nextBefore.value || loading.value) {
      return
    }
    loading.value = true
    try {
      const page = await notificationsApi.list({ before: nextBefore.value, limit: 50 })
      items.value = mergeNewest(items.value, page.items)
      nextBefore.value = page.next_before
      unread.value = page.unread
    } catch {
      // The list shows what it has; "Show older" can be pressed again
    } finally {
      loading.value = false
    }
  }

  /** What came after the newest one we have: what a sleeping or offline browser missed (NOT-2). */
  async function catchUp (): Promise<void> {
    const newest = items.value[0]
    if (!loaded.value || !newest) {
      await load()
      return
    }
    try {
      adopt(await notificationsApi.list({ after: newest.id, limit: 200 }))
    } catch {
      // Still offline or the server is busy: the next reconnect asks again
    }
  }

  async function markRead (id: string): Promise<void> {
    const item = items.value.find(n => n.id === id)
    if (!item || item.read) {
      return
    }
    item.read = true
    unread.value = Math.max(0, unread.value - 1)
    try {
      unread.value = (await notificationsApi.read(id)).unread
    } catch {
      item.read = false
      unread.value++
    }
  }

  async function markAllRead (): Promise<void> {
    const before = items.value.filter(n => !n.read)
    for (const item of before) {
      item.read = true
    }
    unread.value = 0
    try {
      unread.value = (await notificationsApi.readAll()).unread
    } catch {
      for (const item of before) {
        item.read = false
      }
      unread.value = before.length
    }
  }

  function dismissToast (): void {
    arrived.value = null
  }

  function reset (): void {
    socket?.stop()
    items.value = []
    unread.value = 0
    loaded.value = false
    nextBefore.value = null
    error.value = null
    arrived.value = null
    live.value = 'off'
  }

  function build (): RealtimeSocket {
    const scheme = globalThis.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return new RealtimeSocket({
      open: browserSocket,
      url: () => `${scheme}//${globalThis.location.host}/ws`,
      token: accessToken,
      refresh: async () => {
        const result = await refreshSession()
        return result.kind === 'ok' ? 'ok' : (result.kind === 'ended' ? 'ended' : 'offline')
      },
      visible: () => document.visibilityState === 'visible',
      online: () => navigator.onLine,
    }, {
      message: message => {
        if (isNotification(message)) {
          items.value = mergeNewest(items.value, [message.data])
          if (!message.data.read) {
            unread.value++
          }
          arrived.value = message.data
        } else {
          const update = asEntityUpdate(message)
          if (update) {
            emitLive(update)
          }
        }
      },
      open: reconnected => {
        void catchUp()
        if (reconnected) {
          emitLive({ entity: 'reconnected' })
        }
      },
      state: state => {
        live.value = state
      },
    })
  }

  /** Open the channel and load the list. Called once the app shell is up for a signed-in person. */
  function start (): void {
    socket ??= build()
    if (!listening) {
      listening = true
      document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') {
          socket?.wake()
        } else {
          socket?.sleep()
        }
      })
      globalThis.addEventListener('online', () => socket?.wake())
      onSessionChange(session => {
        if (session) {
          socket?.tokenChanged()
        } else {
          reset()
        }
      })
    }
    socket.start()
    if (!loaded.value) {
      void load()
    }
  }

  function stop (): void {
    socket?.stop()
  }

  return {
    items, unread, loaded, loading, error, nextBefore, live, arrived,
    load, loadMore, catchUp, markRead, markAllRead, dismissToast, start, stop, reset,
  }
})
