import { useEffect, useState } from 'react'

import { Button, Field, Modal } from '../../components/ui'
import { ApiError, api } from '../../lib/api'
import { goToRoom } from '../../lib/router'
import { useSession } from '../../state/useSession'
import type { RoomSummary } from '../../types'

/** Entrada a una sala: nombre y, si tiene candado, la contraseña del anfitrión. */
export function JoinDialog({ room, onClose }: { room: RoomSummary; onClose: () => void }) {
  const { playerName, setPlayerName, saveSeat } = useSession()
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    setPassword('')
    setError(null)
    setBusy(false)
  }, [room.code])

  const submit = async () => {
    const name = playerName.trim()
    if (!name) {
      setError('Escribe tu nombre para entrar.')
      return
    }
    if (room.isPrivate && !password) {
      setError('Esta sala es privada: necesitas la contraseña.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const seat = await api.joinRoom(room.code, {
        playerName: name,
        password: room.isPrivate ? password : null,
      })
      saveSeat(seat)
      // Navegar a la sala desmonta este diálogo: no hace falta cerrarlo, y
      // cerrarlo aquí volvería al menú cuando se ha llegado por enlace.
      goToRoom(seat.code)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No he podido entrar en la sala.')
      setBusy(false)
    }
  }

  return (
    <Modal open title={`Entrar en ${room.name}`} onClose={onClose} width={440}>
      <form
        className="stack"
        onSubmit={(event) => {
          event.preventDefault()
          void submit()
        }}
      >
        <div className="join__summary">
          <code className="join__code">{room.code}</code>
          <span className="muted">
            {room.players}/{room.maxPlayers} jugadores{room.isPrivate ? ' · privada' : ' · pública'}
          </span>
        </div>

        <Field
          label="Tu nombre"
          value={playerName}
          maxLength={16}
          autoFocus={!playerName}
          placeholder="Cómo te verán en la mesa"
          onChange={(event) => setPlayerName(event.target.value)}
        />

        {room.isPrivate && (
          <Field
            label="Contraseña de la sala"
            type="password"
            value={password}
            maxLength={32}
            autoFocus={Boolean(playerName)}
            placeholder="La que puso el anfitrión"
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
            {busy ? 'Entrando…' : 'Entrar'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
