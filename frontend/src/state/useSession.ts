import { create } from 'zustand'
import { persist } from 'zustand/middleware'

import { sfx } from '../lib/sfx'
import type { Seat } from '../types'

export interface Settings {
  muted: boolean
  volume: number
  /** Música de fondo del menú principal. */
  music: boolean
  reducedMotion: boolean
}

interface SessionState {
  playerName: string
  settings: Settings
  royalMode: boolean
  /** Asientos por código de sala: permiten volver a entrar tras recargar. */
  seats: Record<string, Seat>
  setPlayerName: (name: string) => void
  patchSettings: (patch: Partial<Settings>) => void
  saveSeat: (seat: Seat) => void
  dropSeat: (code: string) => void
  unlockRoyalMode: () => void
}

export const useSession = create<SessionState>()(
  persist(
    (set) => ({
      playerName: '',
      settings: { muted: false, volume: 0.6, music: true, reducedMotion: false },
      royalMode: false,
      seats: {},

      setPlayerName: (name) => set({ playerName: name.slice(0, 16) }),

      patchSettings: (patch) =>
        set((state) => {
          const settings = { ...state.settings, ...patch }
          sfx.setMuted(settings.muted)
          sfx.setVolume(settings.volume)
          sfx.setMusicEnabled(settings.music)
          return { settings }
        }),

      saveSeat: (seat) => set((state) => ({ seats: { ...state.seats, [seat.code]: seat } })),

      dropSeat: (code) =>
        set((state) => {
          const seats = { ...state.seats }
          delete seats[code]
          return { seats }
        }),

      unlockRoyalMode: () => set({ royalMode: true }),
    }),
    {
      name: 'topcard.session',
      version: 1,
      // Los ajustes guardados antes de existir un campo nuevo (como `music`) no
      // lo traen: se completan con los valores por defecto en vez de quedarse
      // en `undefined`.
      merge: (persisted, current) => {
        const saved = (persisted ?? {}) as Partial<SessionState>
        return { ...current, ...saved, settings: { ...current.settings, ...saved.settings } }
      },
      onRehydrateStorage: () => (state) => {
        if (!state) return
        sfx.setMuted(state.settings.muted)
        sfx.setVolume(state.settings.volume)
        sfx.setMusicEnabled(state.settings.music)
      },
    },
  ),
)

export const seatFor = (code: string): Seat | undefined => useSession.getState().seats[code]
