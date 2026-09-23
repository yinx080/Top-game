import { useEffect, useRef } from 'react'

import { Button } from '../components/ui'
import type { RoomView } from '../types'

/** Fichas de los jugadores: quién está, a quién le toca y quién ya ha hecho lo suyo. */
export function Seats({
  room,
  isHost,
  onKick,
}: {
  room: RoomView
  isHost: boolean
  onKick: (playerId: string) => void
}) {
  const listRef = useRef<HTMLUListElement>(null)

  // En móvil las fichas van en una fila deslizable: centramos la del turno para
  // que no se quede fuera de la vista. Sin desbordamiento no se mueve nada.
  useEffect(() => {
    const list = listRef.current
    const turn = list?.querySelector<HTMLElement>('.seat--turn')
    if (!list || !turn || list.scrollWidth <= list.clientWidth) return
    const offset = turn.getBoundingClientRect().left - list.getBoundingClientRect().left
    list.scrollTo({ left: list.scrollLeft + offset - (list.clientWidth - turn.offsetWidth) / 2, behavior: 'smooth' })
  }, [room.currentPlayerId])

  return (
    <ul className="seats" ref={listRef}>
      {room.players.map((player) => {
        const waitingProposal = room.phase === 'proposing' && !player.proposed
        const waitingVote = room.phase === 'voting' && !player.voted
        const done =
          (room.phase === 'proposing' && player.proposed) ||
          (room.phase === 'voting' && player.voted) ||
          (room.phase === 'placing' && player.hasPlaced)

        return (
          <li
            key={player.id}
            className={[
              'seat',
              player.isCurrent && 'seat--turn',
              !player.connected && 'seat--offline',
              player.id === room.you?.id && 'seat--me',
            ]
              .filter(Boolean)
              .join(' ')}
            style={{ ['--pc' as string]: `var(--p${player.color})` }}
          >
            <span className="seat__dot" aria-hidden="true" />
            <span className="seat__name">{player.name}</span>

            <span className="seat__badges">
              {player.isHost && (
                <span className="seat__badge" title="Anfitrión">
                  ♛
                </span>
              )}
              {!player.connected && (
                <span className="seat__badge seat__badge--warn" title="Desconectado">
                  ⚡
                </span>
              )}
              {done && (
                <span className="seat__badge seat__badge--ok" title="Listo">
                  ✓
                </span>
              )}
              {player.timedOut && <span className="seat__badge seat__badge--warn" title="Tiempo agotado">⏳</span>}
              {(waitingProposal || waitingVote) && player.connected && (
                <span className="seat__badge" title="Pendiente">
                  …
                </span>
              )}
              {room.phase === 'placing' && !player.inRound && (
                <span className="seat__badge" title="Mirando esta ronda">
                  👁
                </span>
              )}
            </span>

            {isHost && player.id !== room.you?.id && (
              <Button
                className="seat__kick"
                size="small"
                variant="ghost"
                title={`Expulsar a ${player.name}`}
                aria-label={`Expulsar a ${player.name}`}
                onClick={() => onKick(player.id)}
              >
                ✕
              </Button>
            )}
          </li>
        )
      })}
    </ul>
  )
}
