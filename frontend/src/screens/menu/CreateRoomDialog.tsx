import { useState } from 'react'

import { Button, Field, Modal, Toggle } from '../../components/ui'
import { ApiError, api } from '../../lib/api'
import { goToRoom } from '../../lib/router'
import { useSession } from '../../state/useSession'

export function CreateRoomDialog({
  open,
  onClose,
  maxPlayersCap,
  defaultMaxPlayers,
}: {
  open: boolean
  onClose: () => void
  maxPlayersCap: number
  defaultMaxPlayers: number
}) {
  const { playerName, setPlayerName, saveSeat } = useSession()
  const [name, setName] = useState('')
  const [isPrivate, setPrivate] = useState(false)
  const [password, setPassword] = useState('')
  const [maxPlayers, setMaxPlayers] = useState(defaultMaxPlayers)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    const roomName = name.trim() || (playerName.trim() ? `Mesa de ${playerName.trim()}` : '')
    if (!playerName.trim()) {
      setError('Escribe tu nombre: es como te verán en la mesa.')
      return
    }
    if (!roomName) {
      setError('Ponle nombre a la sala.')
      return
    }
    if (isPrivate && password.length < 3) {
      setError('La contraseña de una sala privada necesita al menos 3 caracteres.')
      return
    }

    setBusy(true)
    setError(null)
    try {
      const seat = await api.createRoom({
        name: roomName,
        playerName: playerName.trim(),
        isPrivate,
        password: isPrivate ? password : null,
        maxPlayers,
      })
      saveSeat(seat)
      goToRoom(seat.code)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No he podido crear la sala.')
      setBusy(false)
    }
  }

  return (
    <Modal open={open} title="Crear sala" onClose={onClose} width={460}>
      <form
        className="stack"
        onSubmit={(event) => {
          event.preventDefault()
          void submit()
        }}
      >
        <Field
          label="Tu nombre"
          value={playerName}
          maxLength={16}
          placeholder="Anfitrión"
          onChange={(event) => setPlayerName(event.target.value)}
        />

        <Field
          label="Nombre de la sala"
          value={name}
          maxLength={28}
          placeholder={playerName.trim() ? `Mesa de ${playerName.trim()}` : 'Mesa del salón'}
          onChange={(event) => setName(event.target.value)}
        />

        <div className="field">
          <span className="field__label">Jugadores como máximo</span>
          <div className="stepper">
            <Button
              size="small"
              variant="ghost"
              onClick={() => setMaxPlayers((n) => Math.max(2, n - 1))}
              aria-label="Menos jugadores"
            >
              −
            </Button>
            <strong className="stepper__value">{maxPlayers}</strong>
            <Button
              size="small"
              variant="ghost"
              onClick={() => setMaxPlayers((n) => Math.min(maxPlayersCap, n + 1))}
              aria-label="Más jugadores"
            >
              +
            </Button>
          </div>
        </div>

        <div className="stack" style={{ gap: 8 }}>
          <Toggle label="Sala privada (con contraseña)" checked={isPrivate} onChange={setPrivate} />
          <p className="hint">
            Las públicas salen en el menú de inicio. Las privadas sólo aparecen buscándolas, con un
            candado, y piden contraseña para entrar.
          </p>
        </div>

        {isPrivate && (
          <Field
            label="Contraseña"
            type="password"
            value={password}
            maxLength={32}
            placeholder="La que dirás a tus amigos"
            onChange={(event) => setPassword(event.target.value)}
          />
        )}

        {error && <p className="hint hint--error">{error}</p>}

        <div className="row">
          <Button variant="ghost" onClick={onClose}>
            Cancelar
          </Button>
          <span className="spacer" />
          <Button variant="primary" type="submit" disabled={busy}>
            {busy ? 'Creando…' : 'Crear y entrar'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
