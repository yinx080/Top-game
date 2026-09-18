import type { Card } from '../types'

/**
 * Carta de la baraja, recortada del set de Macrovector/Freepik.
 *
 * El volteo es un giro real en 3D con CSS (`preserve-3d`): la cara y el reverso
 * son dos imágenes superpuestas y basta con rotar el contenedor. No hace falta
 * traer three.js sólo para esto.
 */
export function PlayingCard({
  card,
  faceUp,
  width,
  className = '',
  instant = false,
}: {
  card: Card | null
  faceUp: boolean
  width: number
  className?: string
  /** Sin animación de volteo (ajuste de «reducir animaciones»). */
  instant?: boolean
}) {
  const showFace = faceUp && card !== null
  return (
    <div
      className={`pcard ${instant ? 'pcard--instant' : ''} ${className}`}
      style={{ width, height: Math.round(width * 1.42) }}
      data-face-up={showFace ? 'true' : 'false'}
      role="img"
      aria-label={showFace ? describe(card) : 'Carta boca abajo'}
    >
      <div className="pcard__inner">
        <img className="pcard__side pcard__side--back" src="/art/cards/back.png" alt="" />
        {card && (
          <img className="pcard__side pcard__side--front" src={`/art/cards/${card.code}.png`} alt="" />
        )}
      </div>
    </div>
  )
}

const SUIT_NAME: Record<Card['suit'], string> = {
  S: 'picas',
  H: 'corazones',
  D: 'diamantes',
  C: 'tréboles',
}

const RANK_NAME: Record<string, string> = { A: 'As', J: 'J', Q: 'Q', K: 'K' }

function describe(card: Card): string {
  return `${RANK_NAME[card.rank] ?? card.rank} de ${SUIT_NAME[card.suit]}`
}
