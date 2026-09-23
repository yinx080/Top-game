/**
 * Tarjeta para compartir el resultado de una ronda.
 *
 * Se dibuja en un canvas a partir de los datos de la sala, no se hace una
 * captura del tablero: así la imagen sale igual en cualquier móvil, no arrastra
 * el chat ni los botones, y no hace falta ninguna librería.
 *
 * La fila de cartas imita a TableCards: mismo orden que la mesa (izquierda es
 * la posición más baja, o sea la carta más baja cuando el top es correcto),
 * la palabra y el nombre encima, el valor debajo y el fallo marcado en rojo.
 *
 * Para cambiar QUÉ sale en la tarjeta, mira SHARE_CARD justo debajo.
 */

import type { RoomView, TableEntry } from '../types'

/** Qué se dibuja. La tarjeta se recoloca sola con cualquier combinación. */
export const SHARE_CARD = {
  /** La fila de cartas tal y como queda la mesa al acabar la ronda. */
  cards: true,
  /** La palabra que escribió cada jugador, encima de su carta. */
  answers: true,
  /** Victorias y racha de la sala. */
  stats: false,
}

const SIZE = 1080
const MARGIN = 56
const CONTENT_WIDTH = SIZE - MARGIN * 2 - 120
/** Ancho máximo de la fila de cartas. */
const ROW_WIDTH = SIZE - MARGIN * 2 - 80
/** Proporción de las cartas, la misma que usa PlayingCard. */
const CARD_RATIO = 1.42

/** Paleta: los mismos valores que global.css. */
const COLOR = {
  night: '#14121f',
  feltBright: '#14804a',
  feltDeep: '#073d24',
  paper: '#f7f4ec',
  paperDim: '#c9c3b6',
  gold: '#f5b93b',
  red: '#e04e39',
}

/** Colores de jugador (--p0 … --p9 en global.css). */
const PLAYER_COLORS = [
  '#f5b93b',
  '#e04e39',
  '#3fb6a8',
  '#8f7ced',
  '#58c463',
  '#ef7fb4',
  '#4aa3e8',
  '#ef8a3c',
  '#bcd94f',
  '#d59bf6',
]

const DISPLAY = "'Bungee', 'Arial Black', system-ui, sans-serif"
const UI = "'Chakra Petch', 'Segoe UI', system-ui, sans-serif"

export type ShareOutcome = 'shared' | 'downloaded' | 'cancelled' | 'error'

/**
 * Las webfonts se cargan por CSS, y el canvas no espera por ellas: si dibujas
 * antes de tiempo sale todo en Arial. Esto las pide explícitamente.
 */
async function waitForFonts(): Promise<void> {
  if (typeof document === 'undefined' || !document.fonts) return
  try {
    await Promise.all([
      document.fonts.load(`400 64px ${DISPLAY}`),
      document.fonts.load(`600 32px ${UI}`),
    ])
    await document.fonts.ready
  } catch {
    /* si falla, se dibuja con la tipografía de respaldo */
  }
}

/** Carga la imagen de una carta. Devuelve null si no está: la tarjeta sigue saliendo. */
function loadCardImage(code: string): Promise<HTMLImageElement | null> {
  return new Promise((resolve) => {
    const image = new Image()
    image.onload = () => resolve(image)
    image.onerror = () => resolve(null)
    image.src = `/art/cards/${code}.png`
  })
}

/** Parte un texto en líneas que quepan en `maxWidth`, hasta `maxLines`. */
function wrap(
  ctx: CanvasRenderingContext2D,
  text: string,
  maxWidth: number,
  maxLines: number,
): string[] {
  const words = text.trim().split(/\s+/)
  const lines: string[] = []
  let line = ''

  for (const word of words) {
    const candidate = line ? `${line} ${word}` : word
    if (ctx.measureText(candidate).width <= maxWidth || !line) {
      line = candidate
    } else {
      lines.push(line)
      line = word
      if (lines.length === maxLines) break
    }
  }
  if (lines.length < maxLines && line) lines.push(line)

  // Si no cabía todo, se corta la última línea con puntos suspensivos.
  if (lines.length === maxLines) {
    const last = lines[maxLines - 1]
    if (ctx.measureText(last).width > maxWidth || words.join(' ') !== lines.join(' ')) {
      let trimmed = last
      while (trimmed && ctx.measureText(`${trimmed}…`).width > maxWidth) {
        trimmed = trimmed.slice(0, -1).trimEnd()
      }
      lines[maxLines - 1] = `${trimmed}…`
    }
  }
  return lines
}

/** Recorta un texto a una sola línea que quepa en `maxWidth`. */
function truncate(ctx: CanvasRenderingContext2D, text: string, maxWidth: number): string {
  if (ctx.measureText(text).width <= maxWidth) return text
  let trimmed = text
  while (trimmed && ctx.measureText(`${trimmed}…`).width > maxWidth) {
    trimmed = trimmed.slice(0, -1)
  }
  return `${trimmed.trimEnd()}…`
}

function roundedRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  width: number,
  height: number,
  radius: number,
): void {
  if (typeof ctx.roundRect === 'function') {
    ctx.beginPath()
    ctx.roundRect(x, y, width, height, radius)
    return
  }
  ctx.beginPath()
  ctx.rect(x, y, width, height)
}

/**
 * Medidas de la etiqueta que va encima de cada carta.
 *
 * Es la misma caja que `.placed__answer` en room.css: fondo casi negro, borde
 * del color del jugador y esquinas redondeadas.
 */
function rowMetrics(count: number, withAnswers: boolean) {
  const tight = count > 5
  const nameSize = tight ? 20 : 26
  const answerSize = tight ? 18 : 24
  const padY = tight ? 7 : 10
  const padX = tight ? 9 : 13
  const lineGap = 2
  const nameLine = Math.round(nameSize * 1.2)
  const answerLine = Math.round(answerSize * 1.2)
  const boxHeight = padY * 2 + nameLine + (withAnswers ? lineGap + answerLine : 0)
  /** Aire entre la etiqueta y la carta. */
  const gapBox = tight ? 14 : 20

  return {
    gap: tight ? 14 : 24,
    nameSize,
    answerSize,
    padX,
    padY,
    lineGap,
    nameLine,
    answerLine,
    boxHeight,
    gapBox,
    valueSize: tight ? 28 : 36,
    above: boxHeight + gapBox,
    below: tight ? 46 : 58,
  }
}

/** Fondo de la etiqueta, igual que en el tablero. */
const LABEL_BACKDROP = 'rgba(4, 18, 11, 0.82)'

/** Dibuja la tarjeta y la devuelve como PNG. */
export async function renderShareCard(room: RoomView): Promise<Blob> {
  await waitForFonts()

  const entries: TableEntry[] = SHARE_CARD.cards ? room.table : []
  // Las imágenes se piden antes de pintar: dibujar es síncrono.
  const images = await Promise.all(
    entries.map((entry) => (entry.card ? loadCardImage(entry.card.code) : Promise.resolve(null))),
  )

  const canvas = document.createElement('canvas')
  canvas.width = SIZE
  canvas.height = SIZE
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('sin canvas 2d')

  const won = room.outcome === 'win'
  const accent = won ? COLOR.gold : COLOR.red

  // --- Fondo y tapete -------------------------------------------------------
  ctx.fillStyle = COLOR.night
  ctx.fillRect(0, 0, SIZE, SIZE)

  const felt = ctx.createRadialGradient(SIZE / 2, SIZE / 2, 80, SIZE / 2, SIZE / 2, SIZE * 0.72)
  felt.addColorStop(0, COLOR.feltBright)
  felt.addColorStop(1, COLOR.feltDeep)
  roundedRect(ctx, MARGIN, MARGIN, SIZE - MARGIN * 2, SIZE - MARGIN * 2, 44)
  ctx.fillStyle = felt
  ctx.fill()

  // El borde de la tarjeta repite el del final de ronda: oro o rojo.
  ctx.strokeStyle = accent
  ctx.lineWidth = 12
  ctx.stroke()

  ctx.textAlign = 'center'
  const centre = SIZE / 2

  // --- Medir antes de pintar, para centrar el bloque ------------------------
  // El contenido vive entre la marca de arriba y el pie: nunca los invade.
  const SAFE_TOP = 280
  const SAFE_BOTTOM = SIZE - 130
  const available = SAFE_BOTTOM - SAFE_TOP

  // Con la mesa delante, el texto cede sitio: manda la fila de cartas.
  const withCards = entries.length > 0
  const type = {
    eyebrow: withCards ? 50 : 58,
    topicSize: withCards ? 50 : 58,
    topicLine: withCards ? 62 : 74,
    afterTopic: withCards ? 30 : 44,
    verdictSize: withCards ? 60 : 72,
    verdictLine: withCards ? 70 : 86,
  }

  const topicMaxLines = withCards ? 2 : 3
  ctx.font = `400 ${type.topicSize}px ${DISPLAY}`
  const topicLines = wrap(ctx, room.topic?.text ?? 'Sin tema', CONTENT_WIDTH, topicMaxLines)

  const statsHeight = SHARE_CARD.stats ? 72 : 0
  const textHeight =
    type.eyebrow +
    topicLines.length * type.topicLine +
    type.afterTopic +
    type.verdictLine +
    statsHeight

  const metrics = rowMetrics(entries.length, SHARE_CARD.answers)
  let cardWidth = 0
  let cardHeight = 0
  let showAnswers = false

  if (entries.length) {
    const byWidth = (ROW_WIDTH - metrics.gap * (entries.length - 1)) / entries.length
    const spare = available - textHeight - metrics.above - metrics.below - 28
    const byHeight = spare / CARD_RATIO
    // El tope evita que con dos jugadores las cartas salgan descomunales.
    cardWidth = Math.max(56, Math.min(byWidth, byHeight, 230))
    cardHeight = cardWidth * CARD_RATIO
    // En cartas muy pequeñas la palabra no se lee: mejor no ponerla.
    showAnswers = SHARE_CARD.answers && cardWidth >= 84
  }

  const rowHeight = entries.length ? metrics.above + cardHeight + metrics.below + 28 : 0
  const blockHeight = textHeight + rowHeight
  let y = SAFE_TOP + Math.max(0, (available - blockHeight) / 2)

  // --- Marca ----------------------------------------------------------------
  ctx.fillStyle = COLOR.gold
  ctx.font = `400 62px ${DISPLAY}`
  ctx.fillText('TOP CARD', centre, 186)

  ctx.fillStyle = 'rgba(247, 244, 236, 0.55)'
  ctx.font = `600 28px ${UI}`
  ctx.fillText(`SALA ${room.code} · RONDA ${room.round}`, centre, 232)

  // --- Tema -----------------------------------------------------------------
  ctx.fillStyle = COLOR.paperDim
  ctx.font = `600 30px ${UI}`
  ctx.fillText('EL TEMA', centre, y)
  y += type.eyebrow

  ctx.fillStyle = COLOR.paper
  ctx.font = `400 ${type.topicSize}px ${DISPLAY}`
  for (const line of topicLines) {
    ctx.fillText(line, centre, y)
    y += type.topicLine
  }
  y += type.afterTopic

  // --- Veredicto ------------------------------------------------------------
  ctx.fillStyle = accent
  ctx.font = `400 ${type.verdictSize}px ${DISPLAY}`
  ctx.fillText(won ? '¡TOP PERFECTO!' : 'SE ROMPIÓ EL ORDEN', centre, y)
  y += type.verdictLine

  // --- La mesa --------------------------------------------------------------
  if (entries.length) {
    y += 28
    const totalWidth = entries.length * cardWidth + metrics.gap * (entries.length - 1)
    let x = (SIZE - totalWidth) / 2
    const cardTop = y + metrics.above

    entries.forEach((entry, index) => {
      const failed = room.failedPlayerIds.includes(entry.playerId)
      const centreX = x + cardWidth / 2

      // Etiqueta encima de la carta: nombre arriba, palabra debajo, sobre la
      // misma caja oscura con borde de color que usa la mesa.
      const playerColor = failed ? COLOR.red : PLAYER_COLORS[entry.color % PLAYER_COLORS.length]
      const withAnswer = showAnswers && Boolean(entry.answer)
      // Sobresale un poco de la carta, como en la mesa, pero dejando hueco
      // entre etiquetas vecinas.
      const boxWidth = Math.min(cardWidth + 26, cardWidth + metrics.gap - 10)
      const boxHeight =
        metrics.padY * 2 +
        metrics.nameLine +
        (withAnswer ? metrics.lineGap + metrics.answerLine : 0)
      const boxLeft = centreX - boxWidth / 2
      const boxTop = cardTop - metrics.gapBox - boxHeight
      const boxRadius = Math.max(8, Math.round(cardWidth * 0.068))
      const textWidth = boxWidth - metrics.padX * 2

      ctx.save()
      ctx.shadowColor = 'rgba(0, 0, 0, 0.38)'
      ctx.shadowBlur = 16
      ctx.shadowOffsetY = 6
      roundedRect(ctx, boxLeft, boxTop, boxWidth, boxHeight, boxRadius)
      ctx.fillStyle = LABEL_BACKDROP
      ctx.fill()
      ctx.restore()

      roundedRect(ctx, boxLeft, boxTop, boxWidth, boxHeight, boxRadius)
      ctx.strokeStyle = playerColor
      ctx.lineWidth = Math.max(2, Math.round(cardWidth * 0.015))
      ctx.stroke()

      // Con la línea de arriba como referencia cuadra mejor dentro de la caja.
      ctx.textBaseline = 'top'
      ctx.font = `600 ${metrics.nameSize}px ${UI}`
      ctx.fillStyle = playerColor
      ctx.fillText(truncate(ctx, entry.playerName, textWidth), centreX, boxTop + metrics.padY)

      if (withAnswer) {
        ctx.font = `600 ${metrics.answerSize}px ${UI}`
        ctx.fillStyle = COLOR.paper
        ctx.fillText(
          truncate(ctx, entry.answer, textWidth),
          centreX,
          boxTop + metrics.padY + metrics.nameLine + metrics.lineGap,
        )
      }
      ctx.textBaseline = 'alphabetic'

      // La carta.
      const image = images[index]
      ctx.save()
      ctx.shadowColor = 'rgba(0, 0, 0, 0.45)'
      ctx.shadowBlur = 18
      ctx.shadowOffsetY = 8
      if (image) {
        ctx.drawImage(image, x, cardTop, cardWidth, cardHeight)
      } else {
        // Sin imagen, una carta de respaldo con el valor dentro.
        roundedRect(ctx, x, cardTop, cardWidth, cardHeight, cardWidth * 0.09)
        ctx.fillStyle = COLOR.paper
        ctx.fill()
      }
      ctx.restore()

      if (!image && entry.card) {
        ctx.fillStyle = COLOR.night
        ctx.font = `400 ${Math.round(cardWidth * 0.34)}px ${DISPLAY}`
        ctx.fillText(
          entry.card.code === 'joker' ? '🃏' : String(entry.card.value),
          centreX,
          cardTop + cardHeight / 2 + cardWidth * 0.12,
        )
      }

      // El fallo se marca con el mismo rojo que en la mesa.
      if (failed) {
        roundedRect(ctx, x - 3, cardTop - 3, cardWidth + 6, cardHeight + 6, cardWidth * 0.1)
        ctx.strokeStyle = COLOR.red
        ctx.lineWidth = 6
        ctx.stroke()
      }

      // El valor, debajo.
      ctx.font = `400 ${metrics.valueSize}px ${DISPLAY}`
      ctx.fillStyle = failed ? COLOR.red : COLOR.gold
      ctx.fillText(
        entry.card?.code === 'joker' ? '🃏' : String(entry.card?.value ?? '?'),
        centreX,
        cardTop + cardHeight + metrics.valueSize + 10,
      )

      x += cardWidth + metrics.gap
    })

    y = cardTop + cardHeight + metrics.below
  }

  // --- Estadísticas (opcional) ---------------------------------------------
  if (SHARE_CARD.stats) {
    y += 22
    ctx.fillStyle = COLOR.paperDim
    ctx.font = `600 32px ${UI}`
    ctx.fillText(
      `${room.wins} victorias · racha ${room.winStreak} · récord ${room.bestStreak}`,
      centre,
      y,
    )
    y += 50
  }

  // --- Pie ------------------------------------------------------------------
  ctx.fillStyle = 'rgba(247, 244, 236, 0.55)'
  ctx.font = `600 30px ${UI}`
  ctx.fillText('topcards.es', centre, SIZE - 96)

  return await new Promise<Blob>((resolve, reject) => {
    canvas.toBlob(
      (blob) => (blob ? resolve(blob) : reject(new Error('no se pudo generar el PNG'))),
      'image/png',
    )
  })
}

function download(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  // Un respiro antes de soltar la URL: Safari cancela la descarga si se revoca ya.
  window.setTimeout(() => URL.revokeObjectURL(url), 10_000)
}

/** Copia la imagen al portapapeles. Devuelve false si el navegador no deja. */
async function copyToClipboard(blob: Blob): Promise<boolean> {
  try {
    if (typeof ClipboardItem === 'undefined' || !navigator.clipboard?.write) return false
    await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })])
    return true
  } catch {
    return false
  }
}

/**
 * Genera la tarjeta y la comparte.
 *
 * En móvil abre la hoja de compartir del sistema con el PNG adjunto. En
 * escritorio, donde eso casi nunca existe, descarga la imagen y además intenta
 * dejarla en el portapapeles para pegarla directamente en un chat.
 */
export async function shareResult(room: RoomView): Promise<ShareOutcome> {
  let blob: Blob
  try {
    blob = await renderShareCard(room)
  } catch {
    return 'error'
  }

  const filename = `top-card-${room.code}-r${room.round}.png`
  const file = new File([blob], filename, { type: 'image/png' })
  const text = room.outcome === 'win' ? '¡Top perfecto en Top Card!' : 'Se nos rompió el orden en Top Card'

  const nav = navigator as Navigator & {
    canShare?: (data: { files?: File[] }) => boolean
  }

  if (nav.canShare?.({ files: [file] }) && nav.share) {
    try {
      await nav.share({ files: [file], title: 'Top Card', text })
      return 'shared'
    } catch (error) {
      // Cerrar la hoja de compartir no es un fallo: no hay nada que avisar.
      if (error instanceof DOMException && error.name === 'AbortError') return 'cancelled'
      // Cualquier otro problema cae a la descarga de abajo.
    }
  }

  try {
    const copied = await copyToClipboard(blob)
    download(blob, filename)
    return copied ? 'shared' : 'downloaded'
  } catch {
    return 'error'
  }
}
