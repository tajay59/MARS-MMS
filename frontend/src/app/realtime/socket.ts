/*
  The real-time channel to the platform service (PRD NOT-1, NOT-5; TRD §13.4). No Vue, Pinia or
  router here: it takes everything from `SocketDeps`, so Vitest drives it with a fake socket.

      connect → {type:"auth", token} → {type:"ready"} → messages … → close → backoff → connect

  Rules it keeps (pwa skill: ios-safari.md, security.md):

  - The access token is sent as the first message, never in the address (it would reach logs).
  - iOS kills a socket in the background and Android may too. It reconnects when the page is
    visible again and when the network comes back, and tells the owner (`onOpen`) so it can ask
    for what it missed. A hidden page closes its socket after a minute instead of holding it.
  - A refused token (4401) means refresh and try again; if the session has ended, stop.
  - Backoff is 1 s doubling to 30 s with jitter; a good connection starts it over.
  - Nothing here is the system of record: a missed message is found again over HTTP.
*/

export interface SocketEventLike {
  data?: unknown
  code?: number
}

export interface SocketLike {
  send: (data: string) => void
  close: (code?: number) => void
  on: (type: 'open' | 'message' | 'close' | 'error', listener: (event: SocketEventLike) => void) => void
}

/** The browser's WebSocket as a `SocketLike`. */
export function browserSocket (url: string): SocketLike {
  const ws = new WebSocket(url)
  return {
    send: data => ws.send(data),
    close: code => ws.close(code),
    on: (type, listener) => ws.addEventListener(type, event => {
      listener({ data: (event as MessageEvent).data, code: (event as CloseEvent).code })
    }),
  }
}

export type RefreshOutcome = 'ok' | 'ended' | 'offline'
export type SocketState = 'off' | 'connecting' | 'open' | 'waiting'

export interface SocketDeps {
  open: (url: string) => SocketLike
  url: () => string
  token: () => string | null
  refresh: () => Promise<RefreshOutcome>
  visible: () => boolean
  online: () => boolean
  random?: () => number
  setTimer?: (run: () => void, ms: number) => unknown
  clearTimer?: (handle: unknown) => void
  /** How long a hidden page keeps its socket. */
  idleMs?: number
}

export interface SocketHandlers {
  message: (message: Record<string, unknown>) => void
  /** The server said "ready": a first connection or a reconnect. */
  open: (reconnected: boolean) => void
  state?: (state: SocketState) => void
}

export const BACKOFF_START_MS = 1000
export const BACKOFF_MAX_MS = 30_000
export const UNAUTHENTICATED = 4401

export class RealtimeSocket {
  private readonly deps: Required<SocketDeps>
  private readonly handlers: SocketHandlers
  private socket: SocketLike | null = null
  private wanted = false
  private attempt = 0
  private everOpen = false
  private retry: unknown = null
  private idle: unknown = null
  private current: SocketState = 'off'
  private lastRefused = 0

  constructor (deps: SocketDeps, handlers: SocketHandlers) {
    this.deps = {
      random: Math.random,
      setTimer: (run, ms) => setTimeout(run, ms),
      clearTimer: handle => clearTimeout(handle as ReturnType<typeof setTimeout>),
      idleMs: 60_000,
      ...deps,
    }
    this.handlers = handlers
  }

  get state (): SocketState {
    return this.current
  }

  /** Keep a connection while the page is in use. Safe to call twice. */
  start (): void {
    this.wanted = true
    this.connect()
  }

  /** Close for good (logout). */
  stop (): void {
    this.wanted = false
    this.everOpen = false
    this.cancelRetry()
    this.cancelIdle()
    this.drop(1000)
    this.set('off')
  }

  /** The page came back to the front, or the network came back: reconnect now. */
  wake (): void {
    this.cancelIdle()
    if (this.wanted && !this.socket) {
      this.cancelRetry()
      this.connect()
    }
  }

  /** The page went to the background: hold the socket for a minute, then let it go. */
  sleep (): void {
    if (!this.wanted || this.idle !== null) {
      return
    }
    this.idle = this.deps.setTimer(() => {
      this.idle = null
      if (!this.deps.visible()) {
        this.cancelRetry()
        this.drop(1000)
        this.set('waiting')
      }
    }, this.deps.idleMs)
  }

  /** A fresh access token exists: tell the server so the socket outlives the old one. */
  tokenChanged (): void {
    const token = this.deps.token()
    if (this.current === 'open' && this.socket && token) {
      this.socket.send(JSON.stringify({ type: 'auth', token }))
    }
  }

  private connect (): void {
    if (!this.wanted || this.socket || !this.deps.visible() || !this.deps.online()) {
      if (this.wanted && !this.socket) {
        this.set('waiting')
      }
      return
    }
    const token = this.deps.token()
    if (!token) {
      void this.renew()
      return
    }
    this.set('connecting')
    const socket = this.deps.open(this.deps.url())
    this.socket = socket
    socket.on('open', () => {
      if (this.socket === socket) {
        socket.send(JSON.stringify({ type: 'auth', token: this.deps.token() ?? token }))
      }
    })
    socket.on('message', event => {
      if (this.socket === socket) {
        this.receive(socket, event.data)
      }
    })
    socket.on('close', event => {
      if (this.socket === socket) {
        this.socket = null
        this.closed(event.code ?? 1006)
      }
    })
  }

  private receive (socket: SocketLike, data: unknown): void {
    let message: unknown
    try {
      message = JSON.parse(String(data))
    } catch {
      return
    }
    if (typeof message !== 'object' || message === null) {
      return
    }
    const body = message as Record<string, unknown>
    switch (body.type) {
      case 'ready': {
        const reconnected = this.everOpen
        this.everOpen = true
        this.attempt = 0
        this.set('open')
        this.handlers.open(reconnected)
        break
      }
      case 'ping': {
        socket.send(JSON.stringify({ type: 'pong' }))
        break
      }
      default: {
        this.handlers.message(body)
      }
    }
  }

  private closed (code: number): void {
    if (!this.wanted) {
      return
    }
    this.set('waiting')
    if (code === UNAUTHENTICATED) {
      const now = Date.now()
      // A second refusal right after a refresh means the new token was refused too: back off
      if (now - this.lastRefused > 5000) {
        this.lastRefused = now
        void this.renew()
        return
      }
    }
    this.schedule()
  }

  private async renew (): Promise<void> {
    const outcome = await this.deps.refresh()
    if (!this.wanted) {
      return
    }
    if (outcome === 'ended') {
      this.stop()
    } else if (outcome === 'ok') {
      this.connect()
    } else {
      this.schedule()
    }
  }

  private schedule (): void {
    if (!this.wanted || this.retry !== null) {
      return
    }
    const ceiling = Math.min(BACKOFF_MAX_MS, BACKOFF_START_MS * 2 ** this.attempt)
    const wait = Math.max(250, Math.floor(this.deps.random() * ceiling))
    this.attempt++
    this.retry = this.deps.setTimer(() => {
      this.retry = null
      this.connect()
    }, wait)
  }

  private drop (code: number): void {
    const socket = this.socket
    this.socket = null
    try {
      socket?.close(code)
    } catch {
      // Already closed
    }
  }

  private cancelRetry (): void {
    if (this.retry !== null) {
      this.deps.clearTimer(this.retry)
      this.retry = null
    }
  }

  private cancelIdle (): void {
    if (this.idle !== null) {
      this.deps.clearTimer(this.idle)
      this.idle = null
    }
  }

  private set (state: SocketState): void {
    if (state !== this.current) {
      this.current = state
      this.handlers.state?.(state)
    }
  }
}
