import { useEffect, useRef, useState } from 'react'

import { Button, Modal } from '../../components/ui'
import { ApiError, api } from '../../lib/api'
import type { RoomSummary } from '../../types'
import { RoomList } from './RoomList'

/** Menú de búsqueda: encuentra salas por nombre o por código, públicas y privadas. */
export function SearchDialog({
  open,
  onClose,
  onPick,
}: {
  open: boolean
  onClose: () => void
  onPick: (room: RoomSummary) => void
}) {
  const [query, setQuery] = useState('')
  const [rooms, setRooms] = useState<RoomSummary[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!open) return
    inputRef.current?.focus()
    // Pequeño retardo para no disparar una petición por tecla.
    const timer = window.setTimeout(async () => {
      setLoading(true)
      try {
        setRooms(await api.searchRooms(query))
        setError(null)
      } catch (err) {
        setError(err instanceof ApiError ? err.message : 'No he podido buscar.')
      } finally {
        setLoading(false)
      }
    }, 220)
    return () => window.clearTimeout(timer)
  }, [open, query])

  return (
    <Modal open={open} title="Buscar sala" onClose={onClose} width={560}>
      <div className="stack">
        <div className="field">
          <label className="field__label" htmlFor="search-rooms">
            Nombre o código
          </label>
          <div className="field__row">
            <input
              id="search-rooms"
              ref={inputRef}
              className="input"
              value={query}
              maxLength={28}
              placeholder="Mesa del salón, AB3K9P…"
              onChange={(event) => setQuery(event.target.value)}
            />
            {query && (
              <Button variant="ghost" onClick={() => setQuery('')} aria-label="Limpiar búsqueda">
                ✕
              </Button>
            )}
          </div>
          <span className="hint">
            Las salas privadas también aparecen aquí, con candado: para entrar hace falta la
            contraseña del anfitrión.
          </span>
        </div>

        {error && <p className="hint hint--error">{error}</p>}

        <div className="scroll-y" style={{ maxHeight: '46vh' }}>
          <RoomList
            rooms={rooms}
            loading={loading}
            onPick={onPick}
            emptyTitle={query ? 'Ninguna sala coincide' : 'Aún no hay salas'}
            emptyHint={
              query
                ? 'Prueba con otro nombre, o pide el código al anfitrión.'
                : 'Crea una desde el menú y comparte el código.'
            }
          />
        </div>
      </div>
    </Modal>
  )
}
