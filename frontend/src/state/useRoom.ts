import { create } from 'zustand'

import { sfx } from '../lib/sfx'
import { GameSocket, type SocketStatus } from '../lib/socket'
import type { ClientMessage, RoomView, Seat, ServerEvent, ServerMessage } from '../types'
import { useSession } from './useSession'

export interface Toast {
  id: number
  text: string
  tone: 'info' | 'good' | 'bad'
}

interface RoomState {
  status: SocketStatus | 'idle'
  room: RoomView | null
  receivedAt: number
  playerId: string | null
  /** Mensaje del servidor que deja la sala inservible (expulsado, sala cerrada…). */
  fatal: string | null
  toasts: Toast[]
  connect: (seat: Seat) => void
  disconnect: () => void
  leave: () => void
  send: (message: ClientMessage) => void
  toast: (text: string, tone?: Toast['tone']) => void
  dismissToast: (id: number) => void
}

let socket: GameSocket | null = null
let toastId = 0

export const useRoom = create<RoomState>()((set, get) => ({
  status: 'idle',
  room: null,
  receivedAt: 0,
  playerId: null,
  fatal: null,
  toasts: [],

  connect: (seat) => {
    socket?.dispose()
    set({ status: 'connecting', room: null, playerId: seat.playerId, fatal: null, toasts: [] })
    socket = new GameSocket(seat.code, seat.token, {
      onStatus: (status) => set({ status }),
      // El asiento se conserva para que la sala pueda explicar el motivo; se
      // suelta cuando el jugador pulsa «volver al menú».
      onFatal: (reason) => set({ fatal: reason, status: 'closed' }),
      onMessage: (message) => handleMessage(message, set, get),
    })
    socket.connect()
  },

  disconnect: () => {
    socket?.dispose()
    socket = null
    set({ status: 'idle', room: null, playerId: null, fatal: null, toasts: [] })
  },

  leave: () => {
    const code = get().room?.code
    socket?.leave()
    socket = null
    if (code) useSession.getState().dropSeat(code)
    set({ status: 'idle', room: null, playerId: null, fatal: null, toasts: [] })
  },

  send: (message) => {
    if (!socket?.send(message)) {
      get().toast('Sin conexión con la sala, reintentando…', 'bad')
    }
  },

  toast: (text, tone = 'info') => {
    const id = ++toastId
    set((state) => ({ toasts: [...state.toasts.slice(-3), { id, text, tone }] }))
    window.setTimeout(() => get().dismissToast(id), 3600)
  },

  dismissToast: (id) => set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),
}))

type Setter = (partial: Partial<RoomState>) => void

function handleMessage(message: ServerMessage, set: Setter, get: () => RoomState): void {
  switch (message.type) {
    case 'welcome':
      set({ playerId: message.playerId })
      break

    case 'error':
      get().toast(message.message, 'bad')
      break

    case 'state': {
      const previous = get().room
      set({ room: message.room, receivedAt: performance.now() })
      if (message.event) reactToEvent(message.event, message.room, get)
      announceYourTurn(previous, message.room, get)
      break
    }

    case 'drawing': {
      const room = get().room
      set({
        room: room
          ? {
              ...room,
              drawing: room.drawing.some((segment) => segment.id === message.segment.id)
                ? room.drawing
                : [...room.drawing, message.segment],
            }
          : null,
      })
      break
    }

    case 'pong':
      break
  }
}

/** Sonido y aviso para cada evento que manda el servidor. */
function reactToEvent(event: ServerEvent, room: RoomView, get: () => RoomState): void {
  const me = room.you?.name
  switch (event.kind) {
    case 'player_online':
      if (event.name !== me) {
        sfx.play('join')
        get().toast(`${event.name} se ha unido`, 'good')
      }
      break
    case 'player_offline':
      if (event.name !== me) get().toast(`${event.name} se ha desconectado`, 'bad')
      break
    case 'player_left':
      if (event.name !== me) {
        sfx.play('leave')
        get().toast(`${event.name} ha salido de la sala`)
      }
      break
    case 'round_started':
      sfx.play('click')
      get().toast(`Ronda ${event.round}: proponed tema`, 'good')
      break
    case 'voting_open':
      sfx.play('turn')
      break
    case 'topic_chosen':
      sfx.play('deal')
      get().toast(`Tema: ${event.topic}`, 'good')
      break
    case 'card_placed':
      sfx.play('place')
      break
    case 'turn_skipped':
      get().toast('Turno saltado por desconexión')
      break
    case 'turn_timeout':
      get().toast(`Se agotó el tiempo de ${event.name}: turno saltado.`, 'bad')
      break
    case 'reveal':
      sfx.play('flip')
      break
    case 'result':
      // La racha empieza en la segunda victoria seguida, que es cuando se
      // encienden las llamas: esa ronda suena su efecto en lugar de la
      // fanfarria, no los dos.
      if (event.outcome === 'win' && room.winStreak === 2) sfx.play('streak')
      else sfx.play(event.outcome === 'win' ? 'win' : 'lose')
      break
    case 'round_aborted':
      get().toast('Ronda cancelada: no quedan jugadores suficientes', 'bad')
      break
    case 'drawing_cleared':
      get().toast('El anfitrión ha limpiado la mesa')
      break
    default:
      break
  }
}

/** El turno propio es lo único que no conviene perderse: avisa aparte. */
function announceYourTurn(previous: RoomView | null, next: RoomView, get: () => RoomState): void {
  const was = previous?.you?.isCurrent ?? false
  if (!was && next.you?.isCurrent) {
    sfx.play('turn')
    get().toast('¡Te toca colocar!', 'good')
  }
}
