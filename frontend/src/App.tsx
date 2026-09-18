import { useEffect, useState } from 'react'

import { Logo } from './components/Logo'
import { Button, Spinner } from './components/ui'
import { ApiError, api } from './lib/api'
import { goHome, useRoute } from './lib/router'
import { useSession } from './state/useSession'
import { Menu } from './screens/Menu'
import { Room } from './screens/Room'
import { JoinDialog } from './screens/menu/JoinDialog'
import type { RoomSummary } from './types'

export function App() {
  const route = useRoute()
  if (route.name === 'room') return <RoomGate code={route.code} />
  return <Menu />
}

/**
 * Puerta de entrada a una sala.
 *
 * Si ya tenemos asiento guardado (recarga de página, volver atrás) se entra
 * directo; si se llega por enlace compartido, se pide nombre y contraseña.
 */
function RoomGate({ code }: { code: string }) {
  const seat = useSession((state) => state.seats[code])
  const [summary, setSummary] = useState<RoomSummary | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (seat) return
    let cancelled = false
    api
      .room(code)
      .then((room) => !cancelled && setSummary(room))
      .catch((err) =>
        !cancelled && setError(err instanceof ApiError ? err.message : 'No he encontrado esa sala.'),
      )
    return () => {
      cancelled = true
    }
  }, [code, seat])

  if (seat) return <Room seat={seat} />

  return (
    <div className="room room--message">
      <div className="panel panel--center">
        <div className="panel__body stack">
          <Logo size="small" />
          {error ? (
            <>
              <h2 className="panel__title">Sala {code}</h2>
              <p className="hint hint--error">{error}</p>
              <Button variant="primary" onClick={goHome}>
                Volver al menú
              </Button>
            </>
          ) : (
            <Spinner label={`Buscando la sala ${code}…`} />
          )}
        </div>
      </div>
      {summary && <JoinDialog room={summary} onClose={goHome} />}
    </div>
  )
}
