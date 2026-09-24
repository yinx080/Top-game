import { useCallback, useEffect, useState, type CSSProperties } from 'react'

import { Logo } from '../components/Logo'
import { Button, Field } from '../components/ui'
import { ApiError, api, type ServerConfig } from '../lib/api'
import { sfx } from '../lib/sfx'
import { useSession } from '../state/useSession'
import type { RoomSummary } from '../types'
import { CreateRoomDialog } from './menu/CreateRoomDialog'
import { HowToPlay } from './menu/HowToPlay'
import { JoinDialog } from './menu/JoinDialog'
import { RoomList } from './menu/RoomList'
import { SearchDialog } from './menu/SearchDialog'
import { SettingsDialog } from './menu/SettingsDialog'
import '../styles/menu.css'

/** Cartas que flotan de fondo, a lo pantalla de atracción de recreativa. */
const FLOATERS = ['AS', 'KD', '7H', '10C', 'QH', '3D', 'JS', 'back']

type Dialog = 'none' | 'create' | 'search' | 'settings' | 'howto'

export function Menu() {
  const { playerName, setPlayerName, settings, patchSettings } = useSession()
  const musicOn = settings.music && !settings.muted
  const [config, setConfig] = useState<ServerConfig | null>(null)
  const [rooms, setRooms] = useState<RoomSummary[] | null>(null)
  const [hotTopics, setHotTopics] = useState<{ text: string; rounds: number }[]>([])
  const [loading, setLoading] = useState(false)
  const [offline, setOffline] = useState(false)
  const [dialog, setDialog] = useState<Dialog>('none')
  const [joinTarget, setJoinTarget] = useState<RoomSummary | null>(null)
  const [code, setCode] = useState('')
  const [codeError, setCodeError] = useState<string | null>(null)

  // Los refrescos automáticos van en silencio: la animación de carga sólo sale
  // cuando el jugador pulsa ↻ (la primera carga ya tiene su spinner propio).
  // La música sólo suena en el menú: arranca al montarlo y se apaga con un
  // fundido al entrar en una sala.
  useEffect(() => {
    sfx.startMusic()
    return () => sfx.stopMusic()
  }, [])

  const loadRooms = useCallback(async (manual = false) => {
    if (manual) setLoading(true)
    try {
      setRooms(await api.publicRooms())
      setOffline(false)
    } catch {
      setOffline(true)
      setRooms([])
    } finally {
      if (manual) setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadRooms()
    const loadTopics = () => api.hotTopics().then(setHotTopics).catch(() => undefined)
    void loadTopics()
    api.config().then(setConfig).catch(() => undefined)
    // El listado se refresca solo: las salas aparecen y mueren en segundos.
    const timer = window.setInterval(() => { void loadRooms(); void loadTopics() }, 8000)
    const onFocus = () => void loadRooms()
    window.addEventListener('focus', onFocus)
    return () => {
      window.clearInterval(timer)
      window.removeEventListener('focus', onFocus)
    }
  }, [loadRooms])

  const enterByCode = async () => {
    const clean = code.trim().toUpperCase()
    if (!clean) {
      setCodeError('Escribe el código que te han pasado.')
      return
    }
    try {
      const room = await api.room(clean)
      setCodeError(null)
      setCode('')
      setJoinTarget(room)
    } catch (err) {
      setCodeError(err instanceof ApiError ? err.message : 'No he encontrado esa sala.')
    }
  }

  const pickRoom = (room: RoomSummary) => {
    setDialog('none')
    setJoinTarget(room)
  }

  return (
    <div className="menu">
      <div className="menu__backdrop" aria-hidden="true">
        {FLOATERS.map((card, index) => (
          <img
            key={card}
            className="menu__floater"
            src={`/art/cards/${card}.png`}
            alt=""
            draggable={false}
            style={{ '--i': index } as CSSProperties}
          />
        ))}
        {['🍉', '🎸', '🚀', '🐙', '🍒', '💎', '⚽', '🌵'].map((emoji, index) => (
          <span key={emoji} className="menu__floater menu__emoji"
            style={{ '--i': index, top: `${12 + (index * 19) % 76}%` } as CSSProperties}>
            {emoji}
          </span>
        ))}
      </div>

      <button
        type="button"
        className={`menu__music${musicOn ? ' is-on' : ''}`}
        aria-pressed={musicOn}
        aria-label={musicOn ? 'Silenciar la música' : 'Activar la música'}
        title={musicOn ? 'Silenciar la música' : 'Activar la música'}
        onClick={() => {
          // Antes del primer gesto el navegador no deja sonar nada: el ♫ está
          // puesto pero no se oye. Ese primer clic ya la arranca (ver unlock en
          // main.tsx), así que no debe apagarla.
          if (musicOn && !sfx.isMusicPlaying()) return
          patchSettings(musicOn ? { music: false } : { music: true, muted: false })
        }}
      >
        {musicOn ? '♫' : '🔇'}
      </button>

      <main className="menu__inner">
        <header className="menu__header">
          <Logo as="h1" />
          <p className="menu__tagline">
            Ordenad el top entre todos <span className="muted">· sin enseñar las cartas</span>
          </p>
        </header>

        <section className="menu__bar panel">
          <div className="menu__identity">
            <Field
              label="Tu nombre"
              value={playerName}
              maxLength={config?.limits.name ?? 16}
              placeholder="¿Quién eres?"
              onChange={(event) => setPlayerName(event.target.value)}
            />
          </div>

          <div className="menu__actions">
            <Button variant="primary" size="big" onClick={() => setDialog('create')}>
              Crear sala
            </Button>
            <Button size="big" onClick={() => setDialog('search')}>
              🔍 Buscar
            </Button>
            <Button size="big" onClick={() => setDialog('settings')}>
              ⚙ Ajustes
            </Button>
          </div>
        </section>

        <div className="menu__columns">
          <section className="panel menu__rooms">
            <div className="panel__head">
              <h2 className="panel__title">Salas públicas</h2>
              <div className="row">
                {loading && <span className="hint">actualizando…</span>}
                <Button size="small" variant="ghost" onClick={() => void loadRooms(true)}>
                  ↻
                </Button>
              </div>
            </div>
            <div className="panel__body scroll-y menu__rooms-body">
              {offline ? (
                <p className="hint hint--error">
                  No llego al servidor. Comprueba que el backend está levantado en el puerto 8000.
                </p>
              ) : (
                <RoomList
                  rooms={rooms}
                  loading={loading}
                  onPick={pickRoom}
                  emptyTitle="Todavía no hay mesas abiertas"
                  emptyHint="Crea una sala pública y aparecerá aquí para el resto."
                />
              )}
            </div>
          </section>

          <section className="panel menu__topics">
            <div className="panel__head"><h2 className="panel__title">🔥 Hot topics</h2></div>
            <div className="panel__body">
              <p className="hint">Los más jugados en las salas públicas actuales.</p>
              <ol className="hot-topics">
                {(hotTopics.length ? hotTopics : (config?.sampleTopics ?? []).slice(0, 5).map((text) => ({ text, rounds: 0 }))).map((topic) => (
                  <li key={topic.text}><span>{topic.text}</span><small>{topic.rounds ? `${topic.rounds} rondas` : 'Sugerencia'}</small></li>
                ))}
              </ol>
            </div>
          </section>

          <section className="panel menu__rules">
            <div className="panel__head">
              <h2 className="panel__title">Top Cards en 10 segundos</h2>
            </div>
            <div className="panel__body stack" style={{ gap: 10 }}>
              <p className="hint">
                Una carta cada uno, un tema votado entre todos y una palabra por carta. Ganáis si
                al destapar quedan ordenadas de menor a mayor.
              </p>
              <Button size="small" variant="ghost" onClick={() => setDialog('howto')}>
                Ver las reglas
              </Button>
              <a className="menu__guide" href="/como-se-juega">
                Guía completa: cómo se juega
              </a>
            </div>
          </section>

          <section className="panel menu__code">
            <div className="panel__head">
              <h2 className="panel__title">Entrar con código</h2>
            </div>
            <div className="panel__body stack">
              <div className="field__row">
                <input
                  className="input input--code"
                  value={code}
                  maxLength={6}
                  placeholder="AB3K9P"
                  aria-label="Código de sala"
                  onChange={(event) => setCode(event.target.value.toUpperCase())}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') void enterByCode()
                  }}
                />
                <Button variant="primary" onClick={() => void enterByCode()}>
                  Ir
                </Button>
              </div>
              {codeError && <p className="hint hint--error">{codeError}</p>}
              <p className="hint">Sirve igual para salas públicas y privadas.</p>
            </div>
          </section>
        </div>
      </main>

      {/* El menú ocupa toda la pantalla: lo legal sólo aparece al bajar. */}
      <footer className="menu__footer">
        <nav className="menu__legal" aria-label="Información legal">
          <a href="/legal#aviso-legal">Aviso legal</a>
          <a href="/legal#terminos">Términos y condiciones</a>
          <a href="/legal#privacidad">Política de privacidad</a>
          <a href="/legal#cookies">Política de cookies</a>
          <a href="/como-se-juega">Cómo se juega</a>
        </nav>
        <span className="muted">
          Cartas y textura de madera:{' '}
          <a href="https://www.freepik.com" target="_blank" rel="noreferrer noopener">
            Designed by Macrovector / Freepik
          </a>
        </span>
        <span className="muted">© {new Date().getFullYear()} TopCards · Sin cookies ni registro</span>
      </footer>

      <CreateRoomDialog
        open={dialog === 'create'}
        onClose={() => setDialog('none')}
        maxPlayersCap={config?.maxPlayers ?? 10}
        defaultMaxPlayers={config?.defaultMaxPlayers ?? 8}
      />
      <SearchDialog open={dialog === 'search'} onClose={() => setDialog('none')} onPick={pickRoom} />
      <SettingsDialog open={dialog === 'settings'} onClose={() => setDialog('none')} />
      <HowToPlay open={dialog === 'howto'} onClose={() => setDialog('none')} />
      {joinTarget && (
        <JoinDialog
          room={joinTarget}
          onClose={() => {
            setJoinTarget(null)
            void loadRooms()
          }}
        />
      )}
    </div>
  )
}
