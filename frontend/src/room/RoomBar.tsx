import { useState } from 'react'

import { Logo } from '../components/Logo'
import { Button } from '../components/ui'
import { roomLink } from '../lib/router'
import { useSession } from '../state/useSession'
import type { RoomView } from '../types'

/** Barra superior izquierda: identidad de la sala y salidas de emergencia. */
export function RoomBar({ room, onLeave }: { room: RoomView; onLeave: () => void }) {
  const { settings, patchSettings } = useSession()
  const [copied, setCopied] = useState(false)

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(roomLink(room.code))
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1800)
    } catch {
      setCopied(false)
    }
  }

  return (
    <div className="roombar">
      <Logo size="small" />
      <div className="roombar__id">
        <strong className="roombar__name">
          {room.isPrivate && <span title="Sala privada">🔒 </span>}
          {room.name}
        </strong>
        <button type="button" className="roombar__code" onClick={() => void copyLink()}>
          {room.code}
          <span className="roombar__copy">{copied ? '¡copiado!' : 'copiar enlace'}</span>
        </button>
      </div>
      <div className="roombar__tools">
        <Button
          size="small"
          variant="ghost"
          aria-label={settings.muted ? 'Activar sonido' : 'Silenciar'}
          title={settings.muted ? 'Activar sonido' : 'Silenciar'}
          onClick={() => patchSettings({ muted: !settings.muted })}
        >
          {settings.muted ? '🔇' : '🔊'}
        </Button>
        <Button size="small" variant="danger" onClick={onLeave}>
          Salir
        </Button>
      </div>
    </div>
  )
}

/** Cartel del tema, arriba a la derecha durante toda la partida. */
export function TopicBanner({ room }: { room: RoomView }) {
  if (!room.topic) {
    return (
      <div className="topic topic--empty">
        <span className="topic__label">Tema</span>
        <span className="topic__text muted">
          {room.phase === 'lobby' ? 'sin empezar' : 'por decidir'}
        </span>
      </div>
    )
  }

  return (
    <div className="topic">
      <span className="topic__label">Tema · ronda {room.round}</span>
      <span className="topic__text">{room.topic.text}</span>
      {room.topic.author && <span className="topic__author">propuesto por {room.topic.author}</span>}
    </div>
  )
}
