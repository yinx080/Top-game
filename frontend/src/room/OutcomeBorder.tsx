import { useEffect, useState } from 'react'

import { useSession } from '../state/useSession'
import type { RoomView } from '../types'
import '../styles/outcome.css'

/**
 * Borde de color al resolverse la ronda: oro si el grupo gana, rojo si falla.
 *
 * Entra con un fundido y se queda quieto. El latido es el aviso de «se acaba
 * el tiempo» (LowTimeAlert) y conviene que no se parezcan: uno avisa de algo
 * que corre, este cuenta algo que ya ha pasado.
 */
export function OutcomeBorder({ room }: { room: RoomView }) {
  const reducedMotion = useSession((state) => state.settings.reducedMotion)
  const outcome = room.phase === 'result' ? room.outcome : null

  // Se recuerda el último resultado para que el color no desaparezca de golpe
  // mientras el borde se está desvaneciendo.
  const [shown, setShown] = useState<'win' | 'lose' | null>(null)
  useEffect(() => {
    if (outcome) setShown(outcome)
  }, [outcome])

  if (!shown) return null

  const classes = [
    'outcome',
    `outcome--${shown}`,
    outcome ? 'is-on' : '',
    reducedMotion ? 'is-still' : '',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <div className={classes} aria-hidden="true">
      <div className="outcome__edge" />
      {/* Los dos puntos que recorren el borde sólo tienen sentido al ganar. */}
      {shown === 'win' && (
        <>
          <span className="outcome__spot" />
          <span className="outcome__spot outcome__spot--b" />
        </>
      )}
    </div>
  )
}
