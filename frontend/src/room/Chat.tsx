import { AnimatePresence, motion } from 'framer-motion'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'

import { sfx } from '../lib/sfx'
import type { ClientMessage, RoomView } from '../types'

/**
 * Chat de la sala.
 *
 * El historial viaja dentro del estado de la sala, así que quien entra a mitad
 * de partida ve el hilo reciente sin pedir nada aparte. Se pliega a un botón
 * para no tapar la mesa, con contador de mensajes sin leer.
 */
export function Chat({
  room,
  send,
  reducedMotion,
}: {
  room: RoomView
  send: (message: ClientMessage) => void
  reducedMotion: boolean
}) {
  const [open, setOpen] = useState(false)
  const [text, setText] = useState('')
  const [unread, setUnread] = useState(0)
  const logRef = useRef<HTMLUListElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const lastSeen = useRef<number | null>(null)
  const lastSent = useRef(0)

  const messages = room.chat
  const latestId = messages.length ? messages[messages.length - 1].id : 0
  const myId = room.you?.id

  // Mensajes nuevos: suenan y, con el panel plegado, suman al contador. Los
  // propios no cuentan, y el historial que ya había al entrar tampoco: sólo es
  // «nuevo» lo que llega estando tú en la sala.
  useEffect(() => {
    if (lastSeen.current === null) {
      lastSeen.current = latestId
      return
    }
    if (latestId <= lastSeen.current) return

    const since = lastSeen.current
    const fresh = messages.filter((m) => m.id > since && m.playerId !== myId)
    lastSeen.current = latestId
    if (!fresh.length) return

    sfx.play('chat')
    if (!open) setUnread((n) => n + fresh.length)
  }, [latestId, messages, myId, open])

  // Pegado al último mensaje, salvo que estés leyendo hacia arriba.
  useLayoutEffect(() => {
    const log = logRef.current
    if (!log || !open) return
    const nearBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 90
    if (nearBottom) log.scrollTop = log.scrollHeight
  }, [latestId, open])

  useEffect(() => {
    if (open) inputRef.current?.focus()
  }, [open])

  const toggle = () => {
    sfx.play('click')
    setOpen((was) => {
      if (!was) {
        lastSeen.current = latestId
        setUnread(0)
      }
      return !was
    })
  }

  const submit = () => {
    const clean = text.trim()
    if (!clean) return
    // El servidor limita a un mensaje cada medio segundo: aquí lo respetamos
    // para no provocar un error que el jugador no entendería.
    const now = Date.now()
    if (now - lastSent.current < 600) return
    lastSent.current = now
    send({ action: 'chat', text: clean })
    setText('')
  }

  return (
    <aside className={`chat ${open ? 'chat--open' : ''}`}>
      <button
        type="button"
        className="chat__toggle"
        onClick={toggle}
        aria-expanded={open}
        aria-controls="chat-panel"
      >
        <span aria-hidden="true">💬</span>
        <span className="chat__toggleLabel">Chat</span>
        {unread > 0 && !open && (
          <span className="chat__badge" aria-label={`${unread} mensajes sin leer`}>
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            id="chat-panel"
            className="chat__panel"
            initial={reducedMotion ? false : { opacity: 0, y: 14, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.98 }}
            transition={{ duration: 0.18, ease: [0.2, 1.1, 0.4, 1] }}
          >
            <ul className="chat__log scroll-y" ref={logRef} aria-live="polite">
              {messages.length === 0 && (
                <li className="chat__empty">
                  Aquí podéis hablar durante la partida. Cuidado con lo que contáis:
                  vuestras cartas son secretas.
                </li>
              )}
              {messages.map((message) => (
                <li
                  key={message.id}
                  className={`chat__msg ${message.playerId === myId ? 'is-mine' : ''}`}
                  style={{ ['--pc' as string]: `var(--p${message.color})` }}
                >
                  <span className="chat__who">{message.playerName}</span>
                  <span className="chat__text">{message.text}</span>
                </li>
              ))}
            </ul>

            <form
              className="chat__form"
              onSubmit={(event) => {
                event.preventDefault()
                submit()
              }}
            >
              <input
                ref={inputRef}
                className="input chat__input"
                value={text}
                maxLength={room.limits.chat}
                placeholder="Escribe algo…"
                aria-label="Mensaje para la sala"
                onChange={(event) => setText(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Escape') setOpen(false)
                }}
              />
              <button
                type="submit"
                className="chat__send"
                disabled={!text.trim()}
                aria-label="Enviar mensaje"
              >
                ➤
              </button>
            </form>
          </motion.div>
        )}
      </AnimatePresence>
    </aside>
  )
}
