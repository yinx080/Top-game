import { Button, Field, Modal, Toggle } from '../../components/ui'
import { sfx } from '../../lib/sfx'
import { useSession } from '../../state/useSession'

export function SettingsDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { playerName, setPlayerName, settings, patchSettings } = useSession()

  return (
    <Modal open={open} title="Ajustes" onClose={onClose} width={440}>
      <div className="stack">
        <Field
          label="Tu nombre"
          value={playerName}
          maxLength={16}
          placeholder="Cómo te verán en la mesa"
          hint="Se te pedirá igualmente al entrar en una sala."
          onChange={(event) => setPlayerName(event.target.value)}
        />

        <div className="settings__group">
          <Toggle
            label="Sonido"
            checked={!settings.muted}
            onChange={(on) => patchSettings({ muted: !on })}
          />

          <Toggle
            label="Música en el menú"
            checked={settings.music}
            onChange={(on) => patchSettings({ music: on })}
          />

          <div className="field">
            <label className="field__label" htmlFor="volume">
              Volumen
            </label>
            <div className="field__row">
              <input
                id="volume"
                className="slider"
                type="range"
                min={0}
                max={100}
                step={5}
                value={Math.round(settings.volume * 100)}
                disabled={settings.muted}
                onChange={(event) => patchSettings({ volume: Number(event.target.value) / 100 })}
                onMouseUp={() => sfx.play('click')}
              />
              <span className="settings__value">{Math.round(settings.volume * 100)}%</span>
            </div>
          </div>

          <Button size="small" variant="ghost" onClick={() => sfx.play('win')} disabled={settings.muted}>
            Probar sonido
          </Button>
        </div>

        <div className="settings__group">
          <Toggle
            label="Reducir animaciones"
            checked={settings.reducedMotion}
            onChange={(on) => patchSettings({ reducedMotion: on })}
          />
          <p className="hint">
            Deja las cartas quietas y acorta los volteos. Útil si el navegador va justo o si el
            movimiento te molesta.
          </p>
        </div>
      </div>
    </Modal>
  )
}
