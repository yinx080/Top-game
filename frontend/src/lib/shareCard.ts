/**
 * Tarjeta para compartir el resultado de una ronda.
 *
 * Se dibuja en un canvas a partir de los datos de la sala, no se hace una
 * captura del tablero: así la imagen sale igual en cualquier móvil, no arrastra
 * el chat ni los botones, y no hace falta ninguna librería.
 *
 * Para cambiar QUÉ sale en la tarjeta, mira SHARE_CARD justo debajo.
 */

import type { RoomView } from '../types'

/** Qué se dibuja. Pon algo a true y aparece; el resto de la tarjeta se recoloca sola. */
export const SHARE_CARD = {
  /** Nombres y valores en el orden en que se colocaron las cartas. */
  players: false,
  /** La palabra que escribió cada jugador. Necesita `players`. */
  answers: false,
  /** Victorias y racha de la sala. */
  stats: false,
}

const SIZE = 1080
const MARGIN = 56
const CONTENT_WIDTH = SIZE - MARGIN * 2 - 120

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

/** Dibuja la tarjeta y la devuelve como PNG. */
export async function renderShareCard(room: RoomView): Promise<Blob> {
  await waitForFonts()

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
  const SAFE_TOP = 300
  const SAFE_BOTTOM = SIZE - 150
  const available = SAFE_BOTTOM - SAFE_TOP

  ctx.font = `400 58px ${DISPLAY}`
  const topicLines = wrap(ctx, room.topic?.text ?? 'Sin tema', CONTENT_WIDTH, 3)

  const rows = SHARE_CARD.players ? room.table : []
  const statsHeight = SHARE_CARD.stats ? 72 : 0
  const fixedHeight =
    58 + // eyebrow del tema
    topicLines.length * 74 +
    54 + // hueco
    86 + // veredicto
    (rows.length ? 36 : 0) +
    statsHeight

  // Con muchos jugadores las filas se aprietan antes que salirse de la tarjeta,
  // y si aun así no caben, las respuestas se quedan fuera.
  let rowHeight = SHARE_CARD.answers ? 78 : 58
  if (rows.length) {
    const forRows = available - fixedHeight
    rowHeight = Math.max(34, Math.min(rowHeight, Math.floor(forRows / rows.length)))
  }
  const showAnswers = SHARE_CARD.answers && rowHeight >= 68

  const blockHeight = fixedHeight + rows.length * rowHeight
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
  y += 58

  ctx.fillStyle = COLOR.paper
  ctx.font = `400 58px ${DISPLAY}`
  for (const line of topicLines) {
    ctx.fillText(line, centre, y)
    y += 74
  }
  y += 54

  // --- Veredicto ------------------------------------------------------------
  ctx.fillStyle = accent
  ctx.font = `400 72px ${DISPLAY}`
  ctx.fillText(won ? '¡TOP PERFECTO!' : 'SE ROMPIÓ EL ORDEN', centre, y)
  y += 86

  // --- Jugadores (opcional) -------------------------------------------------
  if (rows.length) {
    y += 36
    ctx.font = `600 34px ${UI}`
    for (const entry of rows) {
      const failed = room.failedPlayerIds.includes(entry.playerId)
      const value = entry.card?.code === 'joker' ? '🃏' : String(entry.card?.value ?? '?')

      ctx.textAlign = 'left'
      ctx.fillStyle = failed ? COLOR.red : COLOR.paper
      ctx.fillText(entry.playerName, MARGIN + 110, y)

      ctx.textAlign = 'right'
      ctx.fillStyle = failed ? COLOR.red : COLOR.gold
      ctx.fillText(value, SIZE - MARGIN - 110, y)

      if (showAnswers && entry.answer) {
        ctx.textAlign = 'left'
        ctx.fillStyle = COLOR.paperDim
        ctx.font = `400 26px ${UI}`
        ctx.fillText(entry.answer, MARGIN + 110, y + 32)
        ctx.font = `600 34px ${UI}`
      }

      y += rowHeight
    }
    ctx.textAlign = 'center'
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
