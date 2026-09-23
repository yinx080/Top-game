import { motion } from 'framer-motion'
import { useEffect, useState } from 'react'

import { Button } from '../components/ui'
import { remainingSeconds } from '../lib/clock'
import type { ClientMessage, RoomView } from '../types'
import { ShareResult } from './ShareResult'

type Send = (message: ClientMessage) => void

/** Sala en espera: el código bien grande para dictarlo y el botón de empezar. */
export function LobbyPanel({ room, send }: { room: RoomView; send: Send }) {
  const online = room.players.filter((p) => p.connected).length
  const missing = Math.max(0, room.minPlayers - online)
  const isHost = Boolean(room.you?.isHost)

  return (
    <div className="phase phase--lobby">
      <span className="eyebrow">Sala en espera</span>
      <div className="phase__code">{room.code}</div>
      <p className="hint">
        {online} de {room.maxPlayers} jugadores conectados
        {room.savedTopics > 0 && ` · ${room.savedTopics} temas guardados en esta sala`}
      </p>

      <TimerSettings room={room} send={send} />
      {isHost ? (
        <>
          <Button
            variant="primary"
            size="big"
            disabled={missing > 0}
            onClick={() => send({ action: 'start_round' })}
          >
            {room.round > 0 ? 'Nueva ronda' : 'Empezar ronda'}
          </Button>
          {missing > 0 && (
            <p className="hint">
              Falta{missing > 1 ? 'n' : ''} {missing} jugador{missing > 1 ? 'es' : ''} por conectarse.
            </p>
          )}
        </>
      ) : (
        <p className="hint">Esperando a que el anfitrión empiece la ronda…</p>
      )}
    </div>
  )
}

/** Cada jugador propone un tema para el top, o pasa. */
export function ProposePanel({ room, send }: { room: RoomView; send: Send }) {
  const [text, setText] = useState('')
  const you = room.you
  const pending = room.pendingProposals.length
  const total = room.players.filter((p) => p.connected).length

  if (you?.proposed) {
    return (
      <div className="phase">
        <span className="eyebrow">Propuestas</span>
        <p className="phase__lead">
          {you.proposal ? (
            <>
              Has propuesto <strong>«{you.proposal}»</strong>
            </>
          ) : (
            'Has pasado esta ronda'
          )}
        </p>
        <p className="hint">
          Faltan {pending} de {total} por responder.
        </p>
        {you.isHost && pending > 0 && (
          <Button size="small" variant="ghost" onClick={() => send({ action: 'force' })}>
            Pasar a la votación ya
          </Button>
        )}
      </div>
    )
  }

  const submit = () => send({ action: 'propose', text: text.trim() || null })

  return (
    <div className="phase">
      <span className="eyebrow">Propón el tema de la ronda</span>
      <form
        className="phase__form"
        onSubmit={(event) => {
          event.preventDefault()
          submit()
        }}
      >
        <textarea
          className="input"
          rows={2}
          aria-label="Tema propuesto"
          value={text}
          maxLength={room.limits.topic}
          placeholder="Animales, de menos a más peligrosos…"
          onChange={(event) => setText(event.target.value)}
        />
        <Button variant="primary" type="submit" disabled={!text.trim()}>
          Proponer
        </Button>
        <Button variant="ghost" onClick={() => send({ action: 'propose', text: null })}>
          Pasar
        </Button>
      </form>
      <p className="hint">
        Escribe una escala, no una pregunta. Si tu tema gana la votación, la sala se lo queda para
        futuras rondas. Las propuestas son anónimas. {text.length}/{room.limits.topic}
      </p>
    </div>
  )
}

/** Votación del tema entre los propuestos más algún comodín aleatorio. */
export function VotePanel({ room, send }: { room: RoomView; send: Send }) {
  const you = room.you
  const pending = room.pendingVotes.length
  const colorOf = (playerId: string) =>
    `var(--p${room.players.find((p) => p.id === playerId)?.color ?? 0})`

  return (
    <div className="phase">
      <span className="eyebrow">Votad el tema {pending > 0 && `· faltan ${pending}`}</span>
      <ul className="ballot">
        {room.candidates.map((candidate) => {
          const chosen = you?.vote === candidate.id
          return (
            <li key={candidate.id}>
              <button
                type="button"
                className={`ballot__option ${chosen ? 'is-chosen' : ''}`}
                disabled={Boolean(you?.vote)}
                onClick={() => send({ action: 'vote', candidateId: candidate.id })}
              >
                <span className="ballot__text">{candidate.text}</span>
                <span className="ballot__meta">
                  <span className="tag">
                    {candidate.isRandom ? '🎲 sorpresa' : 'Propuesta anónima'}
                  </span>
                  <span className="ballot__voters">
                    {candidate.voters.map((voterId) => (
                      <span
                        key={voterId}
                        className="ballot__voter"
                        style={{ background: colorOf(voterId) }}
                      />
                    ))}
                  </span>
                </span>
              </button>
            </li>
          )
        })}
      </ul>
      {you?.vote && <p className="hint">Voto registrado. Esperando al resto…</p>}
      {you?.isHost && pending > 0 && (
        <Button size="small" variant="ghost" onClick={() => send({ action: 'force' })}>
          Cerrar votación ya
        </Button>
      )}
    </div>
  )
}

/** Resultado de la ronda: el grupo gana o pierde en bloque. */
export function ResultPanel({ room, send }: { room: RoomView; send: Send }) {
  const won = room.outcome === 'win'
  const failed = room.table.filter((entry) => room.failedPlayerIds.includes(entry.playerId))

  return (
    <motion.div
      className={`phase phase--result ${won ? 'is-win' : 'is-lose'}`}
      initial={{ opacity: 0, scale: 0.94 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ type: 'spring', stiffness: 300, damping: 24 }}
    >
      <h2 className="phase__verdict">{won ? '¡Top perfecto!' : 'Se rompió el orden'}</h2>
      <p className="phase__lead">
        {won
          ? 'Las cartas quedaron ordenadas de menor a mayor. Victoria del grupo.'
           : `Fuera de posición: ${failed.map((entry) => entry.playerName).join(', ')}.`}
      </p>
      <div className="phase__sequence">
        {room.table.map((entry, index) => (
          <span
            key={index}
            className={`phase__num ${room.failedPlayerIds.includes(entry.playerId) ? 'is-break' : ''}`}
          >
            {entry.card?.code === 'joker' ? '🃏' : entry.card?.value}
          </span>
        ))}
      </div>

      {!won && <p className="hint">Se compara cada valor con el top ordenado, sin contar el joker. Un fallo por jugador y ronda.</p>}
      {/* Lo ve todo el mundo, no sólo el anfitrión: cualquiera puede querer la imagen. */}
      <ShareResult room={room} />
      <TimerSettings room={room} send={send} />
      {room.you?.isHost ? (
        <div className="row row--wrap" style={{ justifyContent: 'center' }}>
          <Button variant="primary" onClick={() => send({ action: 'next_round' })}>
            Otra ronda
          </Button>
          <Button variant="ghost" onClick={() => send({ action: 'back_to_lobby' })}>
            Volver al lobby
          </Button>
        </div>
      ) : (
        <p className="hint">Esperando a que el anfitrión lance otra ronda…</p>
      )}
    </motion.div>
  )
}

/** Mientras el servidor voltea las cartas una a una. */
export function RevealPanel({ room }: { room: RoomView }) {
  const [dots, setDots] = useState(1)
  useEffect(() => {
    const timer = window.setInterval(() => setDots((n) => (n % 3) + 1), 420)
    return () => window.clearInterval(timer)
  }, [])

  return (
    <div className="phase phase--reveal">
      <span className="eyebrow">Destapando{'.'.repeat(dots)}</span>
      <p className="hint">
        {room.revealIndex} de {room.table.length} cartas
      </p>
    </div>
  )
}

export function PhaseTimer({ room, receivedAt }: { room: RoomView; receivedAt: number }) {
  const [, tick] = useState(0)
  useEffect(() => {
    if (!room.phaseDeadline) return
    const timer = window.setInterval(() => tick((n) => n + 1), 100)
    return () => window.clearInterval(timer)
  }, [room.phaseDeadline])
  if (!room.phaseDeadline) return null
  const seconds = remainingSeconds(room.phaseDeadline, room.serverNow, receivedAt, performance.now())
  const action = room.phase === 'placing' ? 'colocar' : room.phase === 'proposing' ? 'proponer' : 'votar'
  const current = room.players.find((p) => p.id === room.currentPlayerId)
  return <p className={`phase-timer ${seconds <= 3 ? 'phase-timer--urgent' : ''}`} role="timer">
    ⏳ {seconds} s para {action}{room.phase === 'placing' && ` · ${room.you?.isCurrent ? '¡Tu turno!' : current?.name ?? ''}`}
  </p>
}

export function TimerSettings({ room, send }: { room: RoomView; send: Send }) {
  const [proposal, setProposal] = useState(room.proposalSeconds)
  const [vote, setVote] = useState(room.voteSeconds)
  const [placement, setPlacement] = useState(room.placementSeconds)
  const placing = room.phase === 'placing'
  useEffect(() => {
    setProposal(room.proposalSeconds)
    setVote(room.voteSeconds)
    setPlacement(room.placementSeconds)
  }, [room.proposalSeconds, room.voteSeconds, room.placementSeconds])
  if (!room.you?.isHost) return <p className="hint">Propuestas: {room.proposalSeconds} s · Votos: {room.voteSeconds} s · Colocar: {room.placementSeconds} s</p>
  return (
    <form className="timer-settings" onSubmit={(event) => {
      event.preventDefault()
      send(placing
        ? { action: 'set_timers', placementSeconds: placement }
        : { action: 'set_timers', proposalSeconds: proposal, voteSeconds: vote, placementSeconds: placement })
    }}>
      {!placing && <>
      <label>Proponer (s)<input className="input" type="number" min={5} max={300} required value={Number.isNaN(proposal) ? '' : proposal} onChange={(e) => setProposal(e.target.valueAsNumber)} /></label>
      <label>Votar (s)<input className="input" type="number" min={5} max={300} required value={Number.isNaN(vote) ? '' : vote} onChange={(e) => setVote(e.target.valueAsNumber)} /></label>
      </>}
      <label>Colocar (s)<input className="input" type="number" min={5} max={300} required value={Number.isNaN(placement) ? '' : placement} onChange={(e) => setPlacement(e.target.valueAsNumber)} /></label>
      <Button size="small" type="submit" disabled={proposal === room.proposalSeconds && vote === room.voteSeconds && placement === room.placementSeconds}>Guardar tiempos</Button>
      {placing && <p className="hint timer-settings__note">Duración total del turno. Se mantiene el tiempo ya transcurrido.</p>}
    </form>
  )
}
