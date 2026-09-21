import { useEffect, useState } from 'react'

import { remainingSeconds } from '../lib/clock'
import { sfx } from '../lib/sfx'
import { useSession } from '../state/useSession'
import type { RoomView } from '../types'
import '../styles/low-time.css'

/** Cuando quedan estos segundos de turno: tic-tac + bordes rojos latiendo. */
const WARN_SECONDS = 10
/** Últimos segundos: el latido va el doble de rápido. */
const CRITICAL_SECONDS = 3

export function LowTimeAlert({ room, receivedAt }: { room: RoomView; receivedAt: number }) {
  const reducedMotion = useSession((state) => state.settings.reducedMotion)
  const running = room.phase === 'placing' && room.phaseDeadline !== null && room.currentPlayerId !== null

  // Re-render frecuente sólo mientras hay un turno en marcha.
  const [, tick] = useState(0)
  useEffect(() => {
    if (!running) return
    const timer = window.setInterval(() => tick((n) => n + 1), 100)
    return () => window.clearInterval(timer)
  }, [running, room.phaseDeadline])

  const seconds =
    running && room.phaseDeadline !== null
      ? remainingSeconds(room.phaseDeadline, room.serverNow, receivedAt, performance.now())
      : Infinity
  const active = seconds > 0 && seconds <= WARN_SECONDS

  // `turnKey` reinicia el sonido si un turno acaba y empieza otro sin bajar de WARN_SECONDS
  // (por ejemplo con tiempos de colocación de 10 s o menos).
  const turnKey = `${room.round}:${room.turnIndex}`
  useEffect(() => {
    if (!active) return
    sfx.startTicking()
    return () => sfx.stopTicking()
  }, [active, turnKey])

  const classes = [
    'low-time',
    active ? 'is-on' : '',
    active && seconds <= CRITICAL_SECONDS ? 'is-critical' : '',
    reducedMotion ? 'is-still' : '',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <div className={classes} aria-hidden="true">
      <div className="low-time__pulse" />
    </div>
  )
}