import { AnimatePresence, motion } from 'framer-motion'
import { useEffect, useState } from 'react'

import { Button, Spinner } from '../components/ui'
import { goHome } from '../lib/router'
import { Chat } from '../room/Chat'
import { HandZone } from '../room/HandZone'
import { RoomBar, TopicBanner } from '../room/RoomBar'
import { Seats } from '../room/Seats'
import { TableCards } from '../room/TableCards'
import { LobbyPanel, PhaseTimer, ProposePanel, ResultPanel, RevealPanel, TimerSettings, VotePanel } from '../room/panels'
import { useRoom } from '../state/useRoom'
import { useSession } from '../state/useSession'
import type { Seat } from '../types'
import '../styles/room.css'
import { LowTimeAlert } from '../room/LowTimeAlert'
import { OutcomeBorder } from '../room/OutcomeBorder'

export function Room({ seat }: { seat: Seat }) {
  const { room, receivedAt, status, fatal, connect, disconnect, leave, send, toasts } = useRoom()
  const reducedMotion = useSession((state) => state.settings.reducedMotion)
  const dropSeat = useSession((state) => state.dropSeat)
  const [answer, setAnswer] = useState('')

  const backToMenu = () => {
    dropSeat(seat.code)
    goHome()
  }

  useEffect(() => {
    connect(seat)
    return () => disconnect()
  }, [seat.code, seat.token, connect, disconnect])

  // La palabra sólo vale para la carta que estás colocando ahora mismo.
  useEffect(() => {
    if (room?.you?.hasPlaced || room?.you?.timedOut || room?.phase !== 'placing') setAnswer('')
  }, [room?.you?.hasPlaced, room?.you?.timedOut, room?.phase, room?.round])

  if (fatal) {
    return (
      <div className="room room--message">
        <div className="panel panel--center">
          <div className="panel__body stack">
            <h2 className="panel__title">No se puede seguir en la sala</h2>
            <p className="hint">{fatal}</p>
            <Button variant="primary" onClick={backToMenu}>
              Volver al menú
            </Button>
          </div>
        </div>
      </div>
    )
  }

  if (!room) {
    return (
      <div className="room room--message">
        <div className="panel panel--center">
          <div className="panel__body stack">
            <Spinner label={status === 'connecting' ? 'Entrando en la sala…' : 'Conectando…'} />
            <Button variant="ghost" onClick={backToMenu}>
              Volver al menú
            </Button>
          </div>
        </div>
      </div>
    )
  }

  const you = room.you
  const myTurn = room.phase === 'placing' && Boolean(you?.isCurrent) && !you?.hasPlaced
  const canPlace = myTurn && answer.trim().length > 0
  const currentIsOffline =
    room.phase === 'placing' &&
    !room.players.find((p) => p.id === room.currentPlayerId)?.connected
  // Antes de repartir no hay nada que enseñar en la mesa: el panel de fase
  // ocupa ese espacio y la mesa crece al no haber carta en mano.
  const showTable = room.table.length > 0 || room.phase === 'placing'
  const showHand = Boolean(you) && (room.phase === 'placing' || room.phase === 'revealing')

  const leaveRoom = () => {
    leave()
    goHome()
  }

  return (
    <div className={`room ${showHand ? '' : 'room--nohand'}`}>
      <div className="room__floor" aria-hidden="true" />

      <header className="room-header">
      <RoomBar room={room} onLeave={leaveRoom} />
      <aside className="room-stats" aria-label="Estadísticas de la sala">
        <span>🏆 {room.wins} victorias</span>
        <span>🔥 Racha: {room.winStreak}</span>
        <span>Récord: {room.bestStreak}</span>
        <details className="hall-of-shame">
          <summary>Hall of shame · {room.hallOfShame.length}</summary>
          <div className="hall-of-shame__body">
            <strong>Fallos acumulados en esta sala</strong>
            {room.hallOfShame.length === 0 ? <p>Todavía nadie ha fallado.</p> : (
              <ol>{room.hallOfShame.map((player) => (
                <li key={player.playerId}><span style={{ color: `var(--p${player.color})` }}>{player.name}</span> · {player.failures}</li>
              ))}</ol>
            )}
          </div>
        </details>
      </aside>
      </header>
      <TopicBanner room={room} />
      <PhaseTimer room={room} receivedAt={receivedAt} />
      {room.phase === 'placing' && you?.isHost && (
        <details className="turn-timer-settings">
          <summary>Ajustar tiempo de colocación · {room.placementSeconds} s</summary>
          <TimerSettings room={room} send={send} />
        </details>
      )}

      <div className="table">
        <div className="table__rim">
          <div className="table__felt">
            <span className="table__brand" aria-hidden="true">
              TOP CARD
            </span>

            <div className="table__seats">
              <Seats
                room={room}
                isHost={Boolean(you?.isHost)}
                onKick={(playerId) => send({ action: 'kick', playerId })}
              />
            </div>

            <div className="table__play">
              {showTable && (
                <TableCards
                  room={room}
                  canPlace={canPlace}
                  reducedMotion={reducedMotion}
                  onPlace={(slot) => {
                    send({ action: 'place', slot, answer: answer.trim() })
                  }}
                />
              )}
            </div>

            <div className="table__phase">
              <AnimatePresence mode="wait">
                <motion.div
                  key={room.phase}
                  initial={reducedMotion ? false : { opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  transition={{ duration: 0.18 }}
                >
                  {room.phase === 'lobby' && <LobbyPanel room={room} send={send} />}
                  {room.phase === 'proposing' && <ProposePanel room={room} send={send} />}
                  {room.phase === 'voting' && <VotePanel room={room} send={send} />}
                  {room.phase === 'revealing' && <RevealPanel room={room} />}
                  {room.phase === 'result' && <ResultPanel room={room} send={send} />}
                </motion.div>
              </AnimatePresence>
            </div>
          </div>
        </div>
      </div>

      <HandZone
        room={room}
        answer={answer}
        onAnswerChange={setAnswer}
        reducedMotion={reducedMotion}
      />

      <Chat room={room} send={send} reducedMotion={reducedMotion} />

      {currentIsOffline && you?.isHost && (
        <div className="room__nudge">
          <span>El jugador de turno está desconectado.</span>
          <Button size="small" variant="danger" onClick={() => send({ action: 'skip_turn' })}>
            Saltar turno
          </Button>
        </div>
      )}

      {status !== 'open' && (
        <div className="room__offline" role="status">
          Reconectando con la sala…
        </div>
      )}
        <LowTimeAlert room={room} receivedAt={receivedAt} />
      <OutcomeBorder room={room} />
      <div className="toasts">
        <AnimatePresence initial={false}>
          {toasts.map((toast) => (
            <motion.div
              key={toast.id}
              className={`toast toast--${toast.tone}`}
              initial={{ opacity: 0, x: 24 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 24 }}
              transition={{ duration: 0.18 }}
            >
              {toast.text}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  )
}
