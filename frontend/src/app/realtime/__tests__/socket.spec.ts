import type { RefreshOutcome, SocketEventLike, SocketLike } from '../socket'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { BACKOFF_MAX_MS, RealtimeSocket, UNAUTHENTICATED } from '../socket'

class FakeSocket implements SocketLike {
  sent: string[] = []
  closedWith: number | null = null
  private readonly listeners = new Map<string, (event: SocketEventLike) => void>()

  send (data: string): void {
    this.sent.push(data)
  }

  close (code?: number): void {
    this.closedWith = code ?? 1000
  }

  on (type: string, listener: (event: SocketEventLike) => void): void {
    this.listeners.set(type, listener)
  }

  fire (type: string, event: SocketEventLike = {}): void {
    this.listeners.get(type)?.(event)
  }

  say (message: unknown): void {
    this.fire('message', { data: JSON.stringify(message) })
  }
}

interface Timer { run: () => void, ms: number, id: number }

function setup (options: { token?: string | null, visible?: boolean, online?: boolean, refresh?: RefreshOutcome } = {}) {
  const sockets: FakeSocket[] = []
  const timers: Timer[] = []
  let nextTimer = 1
  const state = {
    token: options.token === undefined ? 'tok-1' : options.token,
    visible: options.visible ?? true,
    online: options.online ?? true,
    refresh: options.refresh ?? 'ok',
  }
  const messages: Record<string, unknown>[] = []
  const opened: boolean[] = []
  const refreshes = vi.fn(async () => {
    if (state.refresh === 'ok') {
      state.token = 'tok-2'
    }
    return state.refresh
  })
  const socket = new RealtimeSocket({
    open: () => {
      const made = new FakeSocket()
      sockets.push(made)
      return made
    },
    url: () => 'wss://mms.test/ws',
    token: () => state.token,
    refresh: refreshes,
    visible: () => state.visible,
    online: () => state.online,
    random: () => 1,
    setTimer: (run, ms) => {
      const id = nextTimer++
      timers.push({ run, ms, id })
      return id
    },
    clearTimer: handle => {
      const at = timers.findIndex(t => t.id === handle)
      if (at !== -1) {
        timers.splice(at, 1)
      }
    },
  }, { message: m => messages.push(m), open: reconnected => opened.push(reconnected) })
  const last = () => sockets.at(-1)!
  const ready = () => {
    last().fire('open')
    last().say({ type: 'ready' })
  }
  return { socket, sockets, timers, state, messages, opened, refreshes, last, ready }
}

describe('the real-time socket', () => {
  beforeEach(() => {
    vi.useRealTimers()
  })

  it('authenticates with the first message, never in the address, and then listens', () => {
    const t = setup()
    t.socket.start()
    expect(t.sockets).toHaveLength(1)
    t.last().fire('open')
    expect(JSON.parse(t.last().sent[0]!)).toEqual({ type: 'auth', token: 'tok-1' })
    expect(t.socket.state).toBe('connecting')
    t.last().say({ type: 'ready' })
    expect(t.socket.state).toBe('open')
    expect(t.opened).toEqual([false])
    t.last().say({ type: 'notification', data: { id: 'n1' } })
    expect(t.messages).toEqual([{ type: 'notification', data: { id: 'n1' } }])
  })

  it('answers the server heartbeat', () => {
    const t = setup()
    t.socket.start()
    t.ready()
    t.last().say({ type: 'ping' })
    expect(JSON.parse(t.last().sent.at(-1)!)).toEqual({ type: 'pong' })
    expect(t.messages).toEqual([])
  })

  it('ignores what is not JSON and what is not an object', () => {
    const t = setup()
    t.socket.start()
    t.ready()
    t.last().fire('message', { data: 'not json' })
    t.last().fire('message', { data: '42' })
    t.last().fire('message', { data: 'null' })
    expect(t.messages).toEqual([])
  })

  it('reconnects with a growing wait that stops at 30 seconds, and starts over once it is ready', () => {
    const t = setup()
    t.socket.start()
    const waits: number[] = []
    for (let i = 0; i < 8; i++) {
      t.last().fire('close', { code: 1006 })
      expect(t.socket.state).toBe('waiting')
      const timer = t.timers.at(-1)!
      waits.push(timer.ms)
      t.timers.splice(t.timers.indexOf(timer), 1)
      timer.run()
    }
    expect(waits.slice(0, 5)).toEqual([1000, 2000, 4000, 8000, 16_000])
    expect(Math.max(...waits)).toBe(BACKOFF_MAX_MS)
    t.ready()
    t.last().fire('close', { code: 1006 })
    expect(t.timers.at(-1)!.ms).toBe(1000)
  })

  it('says it is a reconnect the second time, so the owner can ask for what it missed', () => {
    const t = setup()
    t.socket.start()
    t.ready()
    t.last().fire('close', { code: 1006 })
    t.timers.at(-1)!.run()
    t.ready()
    expect(t.opened).toEqual([false, true])
  })

  it('refreshes the token after a refusal and connects again at once', async () => {
    const t = setup()
    t.socket.start()
    t.ready()
    t.last().fire('close', { code: UNAUTHENTICATED })
    await vi.waitFor(() => expect(t.sockets).toHaveLength(2))
    expect(t.refreshes).toHaveBeenCalledTimes(1)
    t.last().fire('open')
    expect(JSON.parse(t.last().sent[0]!).token).toBe('tok-2')
  })

  it('stops for good when the session has ended', async () => {
    const t = setup({ refresh: 'ended' })
    t.socket.start()
    t.last().fire('close', { code: UNAUTHENTICATED })
    await vi.waitFor(() => expect(t.socket.state).toBe('off'))
    expect(t.sockets).toHaveLength(1)
    expect(t.timers).toHaveLength(0)
  })

  it('backs off instead of looping when a fresh token is refused too', async () => {
    const t = setup()
    t.socket.start()
    t.last().fire('close', { code: UNAUTHENTICATED })
    await vi.waitFor(() => expect(t.sockets).toHaveLength(2))
    t.last().fire('close', { code: UNAUTHENTICATED })
    expect(t.timers.length).toBeGreaterThan(0)
    expect(t.sockets).toHaveLength(2)
  })

  it('sends the new token when the session renews it', () => {
    const t = setup()
    t.socket.start()
    t.ready()
    t.state.token = 'tok-9'
    t.socket.tokenChanged()
    expect(JSON.parse(t.last().sent.at(-1)!)).toEqual({ type: 'auth', token: 'tok-9' })
  })

  it('does not connect while the page is hidden or offline, and does when it comes back', () => {
    const hidden = setup({ visible: false })
    hidden.socket.start()
    expect(hidden.sockets).toHaveLength(0)
    expect(hidden.socket.state).toBe('waiting')
    hidden.state.visible = true
    hidden.socket.wake()
    expect(hidden.sockets).toHaveLength(1)

    const offline = setup({ online: false })
    offline.socket.start()
    expect(offline.sockets).toHaveLength(0)
    offline.state.online = true
    offline.socket.wake()
    expect(offline.sockets).toHaveLength(1)
  })

  it('lets a hidden page go after a minute and takes it back when it is shown again', () => {
    const t = setup()
    t.socket.start()
    t.ready()
    t.state.visible = false
    t.socket.sleep()
    const idle = t.timers.at(-1)!
    expect(idle.ms).toBe(60_000)
    idle.run()
    expect(t.sockets[0]!.closedWith).toBe(1000)
    expect(t.socket.state).toBe('waiting')
    // The close that follows our own close is not a failure to retry
    t.sockets[0]!.fire('close', { code: 1000 })
    expect(t.timers.filter(x => x.ms !== 60_000)).toHaveLength(0)
    t.state.visible = true
    t.socket.wake()
    expect(t.sockets).toHaveLength(2)
  })

  it('keeps the socket when the page comes back before the minute is up', () => {
    const t = setup()
    t.socket.start()
    t.ready()
    t.socket.sleep()
    t.socket.wake()
    expect(t.timers).toHaveLength(0)
    expect(t.sockets).toHaveLength(1)
  })

  it('closes and stays off after stop (logout)', () => {
    const t = setup()
    t.socket.start()
    t.ready()
    t.socket.stop()
    expect(t.sockets[0]!.closedWith).toBe(1000)
    expect(t.socket.state).toBe('off')
    t.sockets[0]!.fire('close', { code: 1000 })
    expect(t.timers).toHaveLength(0)
    t.socket.wake()
    expect(t.sockets).toHaveLength(1)
  })

  it('asks for a token first when it has none', async () => {
    const t = setup({ token: null })
    t.socket.start()
    await vi.waitFor(() => expect(t.sockets).toHaveLength(1))
    expect(t.refreshes).toHaveBeenCalledTimes(1)
  })
})
