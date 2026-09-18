import { motion } from 'framer-motion'

import type { RoomView } from '../types'
import { PlayingCard } from './PlayingCard'

/**
 * La carta que el jugador «tiene en la mano».
 *
 * Aparece abajo, ligeramente girada y levantada, y desaparece en cuanto se
 * coloca: a partir de ahí el jugador sólo ve la mesa con las cartas boca abajo.
 */
export function HandZone({
  room,
  answer,
  onAnswerChange,
  reducedMotion,
}: {
  room: RoomView
  answer: string
  onAnswerChange: (value: string) => void
  reducedMotion: boolean
}) {
  const you = room.you
  if (!you || (room.phase !== 'placing' && room.phase !== 'revealing')) return null

  if (!you.inRound) {
    return (
      <div className="hand hand--note">
        <span className="hand__note">
          👁 Estás mirando esta ronda. Entrarás en la siguiente.
        </span>
      </div>
    )
  }

  if (you.hasPlaced || room.phase === 'revealing') {
    return (
      <div className="hand hand--note">
        <span className="hand__note">
          {room.phase === 'revealing'
            ? 'Destapando de la más baja a la más alta…'
            : 'Carta colocada. A ver si el top cuadra.'}
        </span>
      </div>
    )
  }

  const myTurn = you.isCurrent
  const ready = answer.trim().length > 0

  return (
    <div className={`hand ${myTurn ? 'hand--active' : ''}`}>
      <motion.div
        className="hand__card"
        initial={reducedMotion ? false : { y: 90, rotate: -12, opacity: 0 }}
        animate={{ y: myTurn ? -8 : 16, rotate: myTurn ? 0 : -6, opacity: 1 }}
        transition={{ type: 'spring', stiffness: 260, damping: 26 }}
      >
        <PlayingCard card={you.card} faceUp width={128} instant={reducedMotion} />
        <span className="hand__label">Tu carta</span>
      </motion.div>

      <div className="hand__controls">
        {myTurn ? (
          <>
            <label className="field__label" htmlFor="answer">
              Tu palabra para este top
            </label>
            <input
              id="answer"
              className="input hand__input"
              value={answer}
              maxLength={room.limits.answer}
              autoFocus
              placeholder="Escríbela aquí…"
              onChange={(event) => onAnswerChange(event.target.value)}
            />
            <p className={`hand__hint ${ready ? 'is-ready' : ''}`}>
              {ready
                ? '👉 Ahora elige el hueco de la mesa donde encaja tu carta.'
                : 'Di una palabra que merezca ese puesto en el top.'}
            </p>
          </>
        ) : (
          <p className="hand__hint">
            Le toca a <strong>{nameOf(room, room.currentPlayerId)}</strong>. Mira dónde coloca.
          </p>
        )}
      </div>
    </div>
  )
}

function nameOf(room: RoomView, playerId: string | null): string {
  return room.players.find((p) => p.id === playerId)?.name ?? 'alguien'
}
