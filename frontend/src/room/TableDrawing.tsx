import { useEffect, useRef, useState, type CSSProperties, type PointerEvent as ReactPointerEvent } from 'react'

import type { ClientMessage, DrawingSegment, RoomView } from '../types'

const COLORS = ['#f5b93b', '#e04e39', '#3fb6a8', '#8f7ced', '#58c463', '#ef7fb4', '#4aa3e8', '#ef8a3c', '#bcd94f', '#d59bf6']
const BRUSH_SCALE = [0, 0.0045, 0.009, 0.048]
// La goma va más gorda que el pincel del mismo grosor: borrar con precisión de
// rotulador fino es desesperante.
const ERASER_SCALE = [0, 0.014, 0.03, 0.07]
const SEND_INTERVAL = 110
const MAX_POINTS = 24
const CLEAR_CONFIRM_MS = 3000

type Send = (message: ClientMessage) => void
type Point = { x: number; y: number }
type Tool = 'brush' | 'eraser'
type BrushStroke = Pick<DrawingSegment, 'color' | 'width' | 'erase' | 'points'>

/** Grosor en píxeles de pantalla: escala con la mesa para que todos vean lo mismo. */
function strokeWidth(stroke: Pick<BrushStroke, 'width' | 'erase'>, canvasWidth: number, height: number): number {
  const scale = stroke.erase ? ERASER_SCALE : BRUSH_SCALE
  return Math.max(2.5, Math.min(canvasWidth, height) * scale[stroke.width])
}

export function TableDrawing({ room, send, connected }: { room: RoomView; send: Send; connected: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const cursorRef = useRef<HTMLDivElement>(null)
  const sizeRef = useRef({ width: 0, height: 0 })
  const pendingRef = useRef<Point[]>([])
  const strokeStartRef = useRef(true)
  const optimisticRef = useRef<BrushStroke[]>([])
  const confirmedIdRef = useRef(Math.max(0, ...room.drawing.map((stroke) => stroke.id)))
  const previousDrawingCountRef = useRef(room.drawing.length)
  const redrawRef = useRef<() => void>(() => undefined)
  const undoRef = useRef<() => void>(() => undefined)
  const lastSentAtRef = useRef(0)
  const [active, setActive] = useState(false)
  const [tool, setTool] = useState<Tool>('brush')
  const [color, setColor] = useState(room.you?.color ?? 0)
  const [width, setWidth] = useState<1 | 2 | 3>(2)
  const [confirmClear, setConfirmClear] = useState(false)
  const full = room.drawing.length >= room.limits.drawingSegments
  const erase = tool === 'eraser'
  const hasOwn = room.drawing.some((stroke) => stroke.playerId === room.you?.id)

  const drawPath = (stroke: BrushStroke) => {
    const canvas = canvasRef.current
    const context = canvas?.getContext('2d')
    if (!canvas || !context || stroke.points.length < 2) return
    const { width: canvasWidth, height } = sizeRef.current
    const pixels = stroke.points.map((point) => ({ x: point.x * canvasWidth, y: point.y * height }))
    const path = new Path2D()
    path.moveTo(pixels[0].x, pixels[0].y)
    for (let index = 1; index < pixels.length - 1; index += 1) {
      const point = pixels[index]
      const next = pixels[index + 1]
      path.quadraticCurveTo(point.x, point.y, (point.x + next.x) / 2, (point.y + next.y) / 2)
    }
    path.lineTo(pixels.at(-1)!.x, pixels.at(-1)!.y)

    context.save()
    context.lineCap = 'round'
    context.lineJoin = 'round'
    // La goma recorta lo ya pintado en el lienzo del dibujo; la mesa de debajo
    // es otra capa, así que asoma intacta.
    context.globalCompositeOperation = stroke.erase ? 'destination-out' : 'source-over'
    context.strokeStyle = stroke.erase ? '#000' : COLORS[stroke.color]
    context.lineWidth = strokeWidth(stroke, canvasWidth, height)
    context.stroke(path)
    context.restore()
  }

  const redraw = () => {
    const canvas = canvasRef.current
    const context = canvas?.getContext('2d')
    if (!canvas || !context) return
    context.clearRect(0, 0, sizeRef.current.width, sizeRef.current.height)
    room.drawing.forEach(drawPath)
    optimisticRef.current.forEach(drawPath)
    if (pendingRef.current.length > 1) drawPath({ color, width, erase, points: pendingRef.current })
  }
  redrawRef.current = redraw

  // Deshacer sólo tiene sentido con el trazo ya soltado: a mitad de uno, el
  // servidor aún no lo tiene entero.
  undoRef.current = () => {
    if (!connected || !hasOwn || pendingRef.current.length > 0) return
    send({ action: 'undo_drawing' })
  }

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const observer = new ResizeObserver(() => {
      const rect = canvas.getBoundingClientRect()
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      sizeRef.current = { width: rect.width, height: rect.height }
      canvas.width = Math.max(1, Math.round(rect.width * dpr))
      canvas.height = Math.max(1, Math.round(rect.height * dpr))
      canvas.getContext('2d')?.setTransform(dpr, 0, 0, dpr, 0, 0)
      redrawRef.current()
    })
    observer.observe(canvas)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (previousDrawingCountRef.current > 0 && room.drawing.length === 0) {
      optimisticRef.current = []
    } else {
      const confirmations = room.drawing.filter(
        (stroke) => stroke.playerId === room.you?.id && stroke.id > confirmedIdRef.current,
      ).length
      optimisticRef.current.splice(0, confirmations)
    }
    confirmedIdRef.current = Math.max(confirmedIdRef.current, ...room.drawing.map((stroke) => stroke.id))
    previousDrawingCountRef.current = room.drawing.length
    redraw()
  }, [room.drawing])

  useEffect(() => {
    const desktop = window.matchMedia('(min-width: 701px) and (hover: hover) and (pointer: fine)')
    const stopOnSmallScreen = () => {
      if (!desktop.matches) setActive(false)
    }
    desktop.addEventListener('change', stopOnSmallScreen)
    return () => desktop.removeEventListener('change', stopOnSmallScreen)
  }, [])

  // Atajos mientras se pinta: Escape sale, Ctrl/⌘+Z deshace, B pincel, E goma.
  // Si el foco está en un campo de texto (el chat), el teclado es suyo.
  useEffect(() => {
    if (!active) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setActive(false)
        return
      }
      const target = event.target as HTMLElement | null
      if (target?.closest('input, textarea, [contenteditable="true"]')) return
      if ((event.ctrlKey || event.metaKey) && !event.shiftKey && event.key.toLowerCase() === 'z') {
        event.preventDefault()
        undoRef.current()
      } else if (!event.ctrlKey && !event.metaKey && !event.altKey) {
        if (event.key.toLowerCase() === 'b') setTool('brush')
        if (event.key.toLowerCase() === 'e') setTool('eraser')
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [active])

  useEffect(() => {
    if (!connected) setActive(false)
  }, [connected])

  useEffect(() => {
    if (!active) setConfirmClear(false)
  }, [active])

  useEffect(() => {
    if (!confirmClear) return
    const timer = window.setTimeout(() => setConfirmClear(false), CLEAR_CONFIRM_MS)
    return () => window.clearTimeout(timer)
  }, [confirmClear])

  const pointFrom = (clientX: number, clientY: number, surface: HTMLElement): Point => {
    const rect = surface.getBoundingClientRect()
    return {
      x: Math.max(0, Math.min(1, (clientX - rect.left) / rect.width)),
      y: Math.max(0, Math.min(1, (clientY - rect.top) / rect.height)),
    }
  }

  /** Aro que sigue al ratón con el tamaño real del pincel o de la goma. */
  const moveCursor = (event: ReactPointerEvent<HTMLDivElement>) => {
    const cursor = cursorRef.current
    if (!cursor) return
    const rect = event.currentTarget.getBoundingClientRect()
    const size = strokeWidth({ width, erase }, sizeRef.current.width, sizeRef.current.height)
    cursor.style.width = `${size}px`
    cursor.style.height = `${size}px`
    cursor.style.transform = `translate(${event.clientX - rect.left - size / 2}px, ${event.clientY - rect.top - size / 2}px)`
    cursor.hidden = false
  }

  const collect = (event: ReactPointerEvent<HTMLDivElement>) => {
    const samples = event.nativeEvent.getCoalescedEvents?.() ?? [event.nativeEvent]
    for (const sample of samples.length ? samples : [event.nativeEvent]) {
      const point = pointFrom(sample.clientX, sample.clientY, event.currentTarget)
      const previous = pendingRef.current.at(-1)
      if (!previous) {
        pendingRef.current = [point]
      } else if (previous.x !== point.x || previous.y !== point.y) {
        drawPath({ color, width, erase, points: [previous, point] })
        pendingRef.current.push(point)
      }
    }
  }

  const flush = () => {
    const pending = pendingRef.current
    if (pending.length < 2) return
    const points = pending.length <= MAX_POINTS
      ? pending
      : Array.from({ length: MAX_POINTS }, (_, index) => pending[Math.round(index * (pending.length - 1) / (MAX_POINTS - 1))])
    optimisticRef.current.push({ color, width, erase, points })
    send({ action: 'draw', points, color, width, erase, start: strokeStartRef.current })
    strokeStartRef.current = false
    pendingRef.current = [pending.at(-1)!]
    lastSentAtRef.current = performance.now()
  }

  const finishStroke = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (active && pendingRef.current.length > 0) {
      collect(event)
      flush()
    }
    pendingRef.current = []
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId)
    }
  }

  return (
    <>
      <canvas
        ref={canvasRef}
        className="table-drawing"
        aria-hidden="true"
      />
      <div
        className={`table-drawing-input${active ? ' is-active' : ''}`}
        aria-label={active ? 'Lienzo de dibujo activo. Pulsa Escape para salir.' : undefined}
        aria-hidden={!active}
        onPointerDown={(event) => {
          if (!active || event.button !== 0 || full) return
          pendingRef.current = [pointFrom(event.clientX, event.clientY, event.currentTarget)]
          strokeStartRef.current = true
          lastSentAtRef.current = performance.now()
          event.currentTarget.setPointerCapture(event.pointerId)
        }}
        onPointerMove={(event) => {
          if (!active) return
          moveCursor(event)
          if (pendingRef.current.length === 0 || !event.currentTarget.hasPointerCapture(event.pointerId)) return
          collect(event)
          if (performance.now() - lastSentAtRef.current >= SEND_INTERVAL) flush()
        }}
        onPointerLeave={() => {
          if (cursorRef.current) cursorRef.current.hidden = true
        }}
        onPointerUp={finishStroke}
        onPointerCancel={(event) => {
          pendingRef.current = []
          if (event.currentTarget.hasPointerCapture(event.pointerId)) {
            event.currentTarget.releasePointerCapture(event.pointerId)
          }
        }}
      >
        {active && (
          <div
            ref={cursorRef}
            className={`table-drawing-cursor${erase ? ' is-eraser' : ''}`}
            style={{ '--brush-color': COLORS[color] } as CSSProperties}
            hidden
          />
        )}
      </div>
      <div className={`drawing-tools${active ? ' is-active' : ''}`}>
        {active && (
          <div className="drawing-tools__brush">
            <div className="drawing-tools__modes" role="group" aria-label="Herramienta">
              <button
                type="button"
                className={`drawing-tools__mode${!erase ? ' is-selected' : ''}`}
                aria-pressed={!erase}
                title="Pincel (B)"
                onClick={() => setTool('brush')}
              >
                ✏️ Pincel
              </button>
              <button
                type="button"
                className={`drawing-tools__mode${erase ? ' is-selected' : ''}`}
                aria-pressed={erase}
                title="Goma de borrar (E)"
                onClick={() => setTool('eraser')}
              >
                🧽 Goma
              </button>
            </div>
            <div
              className={`drawing-tools__colors${erase ? ' is-disabled' : ''}`}
              role="group"
              aria-label="Color del pincel"
            >
              {COLORS.map((option, index) => (
                <button
                  key={option}
                  type="button"
                  className={`drawing-tools__color${color === index ? ' is-selected' : ''}`}
                  style={{ '--brush-color': option } as CSSProperties}
                  aria-label={`Color ${index + 1}`}
                  aria-pressed={color === index}
                  onClick={() => {
                    setColor(index)
                    setTool('brush')
                  }}
                />
              ))}
            </div>
            <label className="drawing-tools__width">
              Grosor
              <input
                type="range"
                min="1"
                max="3"
                step="1"
                value={width}
                onChange={(event) => setWidth(Number(event.target.value) as 1 | 2 | 3)}
              />
            </label>
            <div className="drawing-tools__actions">
              <button
                type="button"
                className="drawing-tools__action"
                disabled={!connected || !hasOwn}
                title="Deshacer tu último trazo (Ctrl+Z)"
                onClick={() => undoRef.current()}
              >
                ↶ Deshacer
              </button>
              <button
                type="button"
                className="drawing-tools__action"
                disabled={!connected || !hasOwn}
                title="Borrar todo lo que has pintado tú, sin tocar lo de los demás"
                onClick={() => send({ action: 'clear_own_drawing' })}
              >
                Borrar lo mío
              </button>
              {room.you?.isHost && (
                <button
                  type="button"
                  className={`drawing-tools__action drawing-tools__action--danger${confirmClear ? ' is-armed' : ''}`}
                  disabled={!connected || room.drawing.length === 0}
                  title="Borra los dibujos de todos los jugadores"
                  onClick={() => {
                    if (!confirmClear) {
                      setConfirmClear(true)
                      return
                    }
                    setConfirmClear(false)
                    send({ action: 'clear_drawing' })
                  }}
                >
                  {confirmClear ? '¿Borrar todo?' : 'Limpiar mesa'}
                </button>
              )}
            </div>
            {full && (
              <p className="drawing-tools__note">
                La mesa está llena: deshaz o borra trazos para seguir pintando.
              </p>
            )}
          </div>
        )}
        <button
          type="button"
          className={`drawing-tools__button${active ? ' is-active' : ''}`}
          aria-pressed={active}
          disabled={!connected}
          title="Dibujar sobre la mesa"
          onClick={() => setActive((value) => !value)}
        >
          {active ? 'Terminar' : 'Pintar'}
        </button>
      </div>
    </>
  )
}
