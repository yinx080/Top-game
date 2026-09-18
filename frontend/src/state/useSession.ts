import { create } from 'zustand'
import { persist } from 'zustand/middleware'

import { sfx } from '../lib/sfx'
import type { Seat } from '../types'

export interface Settings {
  muted: boolean
  volume: number
  reducedMotion: boolean
}

interface SessionState {
  playerName: string
  settings: Settings
  /** Asientos por código de sala: permiten volver a entrar tras recargar. */
  seats: Record<string, Seat>
  setPlayerName: (name: string) => void
  patchSettings: (patch: Partial<Settings>) => void
  saveSeat: (seat: Seat) => void
  dropSeat: (code: string) => void
}

export const useSession = create<SessionState>()(
  persist(
    (set) => ({
      playerName: '',
      settings: { muted: false, volume: 0.6, reducedMotion: false },
      seats: {},

      setPlayerName: (name) => set({ playerName: name.slice(0, 16) }),

      patchSettings: (patch) =>
        set((state) => {
          const settings = { ...state.settings, ...patch }
          sfx.setMuted(settings.muted)
          sfx.setVolume(settings.volume)
          return { settings }
        }),

      saveSeat: (seat) => set((state) => ({ seats: { ...state.seats, [seat.code]: seat } })),

      dropSeat: (code) =>
        set((state) => {
          const seats = { ...state.seats }
          delete seats[code]
          return { seats }
        }),
    }),
    {
      name: 'topcard.session',
      version: 1,
      onRehydrateStorage: () => (state) => {
        if (!state) return
        sfx.setMuted(state.settings.muted)
        sfx.setVolume(state.settings.volume)
      },
    },
  ),
)

export const seatFor = (code: string): Seat | undefined => useSession.getState().seats[code]
