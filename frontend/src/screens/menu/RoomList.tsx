import { EmptyState, Spinner } from '../../components/ui'
import type { RoomSummary } from '../../types'

const PHASE_LABEL: Record<RoomSummary['phase'], string> = {
  lobby: 'En el lobby',
  proposing: 'Proponiendo tema',
  voting: 'Votando tema',
  placing: 'Colocando cartas',
  revealing: 'Destapando',
  result: 'Viendo resultado',
}

export function RoomList({
  rooms,
  loading,
  onPick,
  emptyTitle,
  emptyHint,
}: {
  rooms: RoomSummary[] | null
  loading: boolean
  onPick: (room: RoomSummary) => void
  emptyTitle: string
  emptyHint: string
}) {
  if (rooms === null || (loading && rooms.length === 0)) {
    return <Spinner label="Buscando salas…" />
  }
  if (rooms.length === 0) {
    return (
      <EmptyState icon="🃏" title={emptyTitle}>
        {emptyHint}
      </EmptyState>
    )
  }

  return (
    <ul className="rooms">
      {rooms.map((room) => {
        const full = room.players >= room.maxPlayers
        return (
          <li key={room.code}>
            <button
              type="button"
              className="rooms__item"
              onClick={() => onPick(room)}
              disabled={full}
              title={full ? 'La sala está llena' : `Entrar en ${room.name}`}
            >
              <span className="rooms__icon" aria-hidden="true">
                {room.isPrivate ? '🔒' : '🂠'}
              </span>
              <span className="rooms__main">
                <span className="rooms__name">{room.name}</span>
                <span className="rooms__meta">
                  <code>{room.code}</code>
                  <span>·</span>
                  <span>{PHASE_LABEL[room.phase]}</span>
                  {room.round > 0 && (
                    <>
                      <span>·</span>
                      <span>ronda {room.round}</span>
                    </>
                  )}
                </span>
              </span>
              <span className="rooms__side">
                <span className={`tag ${room.inGame ? 'tag--live' : ''}`}>
                  {room.players}/{room.maxPlayers}
                </span>
                {room.isPrivate && <span className="tag tag--locked">Privada</span>}
                {full && <span className="tag">Llena</span>}
              </span>
            </button>
          </li>
        )
      })}
    </ul>
  )
}
