import { useEffect, useRef, useState } from 'react'

import { Button } from '../components/ui'
import { shareResult, type ShareOutcome } from '../lib/shareCard'
import type { RoomView } from '../types'

/** Mensaje bajo el botón según cómo haya acabado el intento. */
const FEEDBACK: Partial<Record<ShareOutcome, string>> = {
  shared: '¡Listo! Imagen preparada.',
  downloaded: 'Imagen descargada.',
  error: 'No se pudo crear la imagen.',
}

/** Botón de compartir el resultado de la ronda como imagen. */
export function ShareResult({ room }: { room: RoomView }) {
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<ShareOutcome | null>(null)
  const timer = useRef<number | null>(null)

  useEffect(
    () => () => {
      if (timer.current) window.clearTimeout(timer.current)
    },
    [],
  )

  const onShare = async () => {
    if (busy) return
    setBusy(true)
    setResult(null)
    const outcome = await shareResult(room)
    setBusy(false)
    // Cancelar la hoja de compartir es una decisión del jugador, no un aviso.
    if (outcome === 'cancelled') return
    setResult(outcome)
    if (timer.current) window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setResult(null), 3000)
  }

  return (
    <div className="stack">
      <Button variant="ghost" onClick={onShare} disabled={busy}>
        {busy ? 'Preparando…' : 'Compartir resultado'}
      </Button>
      {result && FEEDBACK[result] && (
        <p className="hint" role="status">
          {FEEDBACK[result]}
        </p>
      )}
    </div>
  )
}
