import { AnimatePresence, motion } from 'framer-motion'
import { Fragment } from 'react'

import { sfx } from '../lib/sfx'
import type { RoomView, TableEntry } from '../types'
import { PlayingCard } from './PlayingCard'

/** El ancho de carta se ajusta al número de cartas para que la fila quepa. */
function cardWidth(count: number): number {
  if (count <= 3) return 132
  if (count <= 5) return 116
  if (count <= 7) return 100
  if (count <= 9) return 88
  return 78
}

export function TableCards({
  room,
  canPlace,
  onPlace,
  reducedMotion,
}: {
  room: RoomView
  /** Es mi turno y ya he escrito la palabra: los huecos están activos. */
  canPlace: boolean
  onPlace: (slot: number) => void
  reducedMotion: boolean
}) {
  const { table, phase } = room
  const width = cardWidth(table.length + (canPlace ? 1 : 0))

  if (table.length === 0) {
    return (
      <div className="table__empty">
        <span className="table__emptyText">
          {canPlace ? (
            <>
              Tu carta abre el top:{' '}
              <button type="button" className="slot slot--first" onClick={() => onPlace(0)}>
                <span className="slot__mark">+</span> colocar aquí
              </button>
            </>
          ) : phase === 'placing' ? (
            'La mesa está vacía: la primera carta abre el top'
          ) : (
            'Mesa vacía'
          )}
        </span>
      </div>
    )
  }

  return (
    <div className="tablecards" style={{ ['--card-w' as string]: `min(${width}px, var(--card-max, ${width}px))` }}>
      {table.map((entry, index) => (
        <Fragment key={entry.playerId}>
          <Slot index={index} active={canPlace} onPlace={onPlace} />
          <PlacedCard
            entry={entry}
            next={table.slice(index + 1).find((item) => item.card?.code !== 'joker')}
            width={width}
            isBreak={phase === 'result' && room.failedPlayerIds.includes(entry.playerId)}
            showValue={phase === 'result'}
            reducedMotion={reducedMotion}
          />
        </Fragment>
      ))}
      <Slot index={table.length} active={canPlace} onPlace={onPlace} />
    </div>
  )
}

function PlacedCard({
  entry,
  next,
  width,
  isBreak,
  showValue,
  reducedMotion,
}: {
  entry: TableEntry
  next: TableEntry | undefined
  width: number
  isBreak: boolean
  showValue: boolean
  reducedMotion: boolean
}) {
  // Sólo se puede juzgar el orden entre dos cartas ya destapadas.
  const bothUp = entry.revealed && entry.card && entry.card.code !== 'joker' && next?.revealed && next.card
  const ordered = bothUp ? entry.card!.value <= next!.card!.value : null

  return (
    <motion.div
      className="placed"
      layout={!reducedMotion}
      initial={reducedMotion ? false : { opacity: 0, y: -28, scale: 0.9 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ type: 'spring', stiffness: 420, damping: 32 }}
      style={{ ['--pc' as string]: `var(--p${entry.color})` }}
    >
      {/* La respuesta va siempre encima de la carta y visible para todos. */}
      <div className="placed__answer">
        <span className="placed__word">{entry.answer}</span>
        <span className="placed__owner">{entry.playerName}</span>
      </div>

      <div className={`placed__card ${isBreak ? 'is-break' : ''}`}>
        <PlayingCard card={entry.card} faceUp={entry.revealed} width={width} instant={reducedMotion} />
        <AnimatePresence>
          {showValue && entry.card && (
            <motion.span
              className="placed__value"
              initial={{ opacity: 0, scale: 0.6 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0 }}
            >
               {entry.card.code === 'joker' ? '🃏' : entry.card.value}
            </motion.span>
          )}
        </AnimatePresence>
      </div>

      {ordered !== null && (
        <span className={`placed__check ${ordered ? 'is-ok' : 'is-bad'}`} aria-hidden="true">
          {ordered ? '≤' : '>'}
        </span>
      )}
    </motion.div>
  )
}

function Slot({
  index,
  active,
  onPlace,
}: {
  index: number
  active: boolean
  onPlace: (slot: number) => void
}) {
  if (!active) return null
  return (
    <button
      type="button"
      className="slot"
      aria-label={`Colocar la carta en la posición ${index + 1}`}
      onClick={() => {
        sfx.play('place')
        onPlace(index)
      }}
    >
      <span className="slot__mark">+</span>
    </button>
  )
}
