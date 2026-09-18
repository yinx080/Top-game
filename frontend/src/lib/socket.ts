import type { ClientMessage, ServerMessage } from '../types'

export type SocketStatus = 'connecting' | 'open' | 'closed'

/** Cierres de los que no tiene sentido reintentar: la sala o el asiento ya no existen. */
const FATAL_CLOSE_CODES = new Set([4401, 4403, 4404])

interface Handlers {
  onMessage: (message: ServerMessage) => void
  onStatus: (status: SocketStatus) => void
  onFatal: (reason: string) => void
}

/**
 * Conexión con la sala. Se reconecta sola con espera creciente, porque en una
 * partida de varios minutos el wifi se cae más de lo que uno quisiera.
 */
export class GameSocket {
  private ws: WebSocket | null = null
  private attempts = 0
  private retryTimer: number | null = null
  private pingTimer: number | null = null
  private disposed = false
  private lastError: string | null = null

  constructor(
    private readonly code: string,
    private readonly token: string,
    private readonly handlers: Handlers,
  ) {}

  connect(): void {
    if (this.disposed) return
    this.clearTimers()
    this.handlers.onStatus('connecting')

    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${protocol}//${location.host}/ws/${encodeURIComponent(this.code)}?token=${encodeURIComponent(this.token)}`
    const ws = new WebSocket(url)
    this.ws = ws

    ws.onopen = () => {
      this.attempts = 0
      this.lastError = null
      this.handlers.onStatus('open')
      this.pingTimer = window.setInterval(() => this.send({ action: 'ping' }), 25_000)
    }

    ws.onmessage = (event) => {
      let message: ServerMessage
      try {
        message = JSON.parse(event.data as string)
      } catch {
        return
      }
      // Guardamos el último error por si el servidor cierra justo después: así
      // podemos explicar *por qué* se ha cerrado en lugar de reintentar a ciegas.
      if (message.type === 'error') this.lastError = message.message
      this.handlers.onMessage(message)
    }

    ws.onclose = (event) => {
      this.clearTimers()
      this.ws = null
      if (this.disposed) return
      this.handlers.onStatus('closed')
      if (FATAL_CLOSE_CODES.has(event.code)) {
        this.disposed = true
        this.handlers.onFatal(this.lastError ?? 'La sala ya no está disponible.')
        return
      }
      this.attempts += 1
      const wait = Math.min(1000 * 2 ** (this.attempts - 1), 10_000)
      this.retryTimer = window.setTimeout(() => this.connect(), wait)
    }

    ws.onerror = () => ws.close()
  }

  send(message: ClientMessage): boolean {
    if (this.ws?.readyState !== WebSocket.OPEN) return false
    this.ws.send(JSON.stringify(message))
    return true
  }

  /** Avisa al servidor de que el jugador abandona y cierra sin reintentar. */
  leave(): void {
    this.send({ action: 'leave' })
    this.dispose()
  }

  dispose(): void {
    this.disposed = true
    this.clearTimers()
    this.ws?.close()
    this.ws = null
  }

  private clearTimers(): void {
    if (this.retryTimer !== null) window.clearTimeout(this.retryTimer)
    if (this.pingTimer !== null) window.clearInterval(this.pingTimer)
    this.retryTimer = this.pingTimer = null
  }
}
