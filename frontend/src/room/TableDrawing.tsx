import { useEffect, useRef, useState, type CSSProperties, type PointerEvent as ReactPointerEvent } from 'react'

import type { ClientMessage, DrawingSegment, RoomView } from '../types'

const COLORS = ['#f5b93b', '#e04e39', '#3fb6a8', '#8f7ced', '#58c463', '#ef7fb4', '#4aa3e8', '#ef8a3c', '#bcd94f', '#d59bf6']
const BRUSH_SCALE = [0, 0.0045, 0.009, 0.048]
const SEND_INTERVAL = 110
const MAX_POINTS = 24

type Send = (message: ClientMessage) => void
type Point = { x: number; y: number }

export function TableDrawing({ room, send, connected }: { room: RoomView; send: Send; connected: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const sizeRef = useRef({ width: 0, height: 0 })
  const pendingRef = useRef<Point[]>([])
  const lastSentAtRef = useRef(0)
  const [active, setActive] = useState(false)
  const [color, setColor] = useState(room.you?.color ?? 0)
  const [width, setWidth] = useState<1 | 2 | 3>(2)
  const full = room.drawing.length >= room.limits.drawingSegments

  const drawPath = (stroke: Pick<DrawingSegment, 'color' | 'width' | 'points'>) => {
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

    const brushWidth = Math.max(2.5, Math.min(canvasWidth, height) * BRUSH_SCALE[stroke.width])
    context.save()
    context.lineCap = 'round'
    context.lineJoin = 'round'
    context.strokeStyle = COLORS[stroke.color]
    context.lineWidth = brushWidth
    context.stroke(path)
    context.restore()
  }

  const redraw = () => {
    const canvas = canvasRef.current
    const context = canvas?.getContext('2d')
    if (!canvas || !context) return
    context.clearRect(0, 0, sizeRef.current.width, sizeRef.current.height)
    room.drawing.forEach(drawPath)
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
      redraw()
    })
    observer.observe(canvas)
    return () => observer.disconnect()
  })

  useEffect(redraw, [room.drawing])

  useEffect(() => {
    const desktop = window.matchMedia('(min-width: 701px) and (hover: hover) and (pointer: fine)')
    const stopOnSmallScreen = () => {
      if (!desktop.matches) setActive(false)
    }
    const stopOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setActive(false)
    }
    desktop.addEventListener('change', stopOnSmallScreen)
    window.addEventListener('keydown', stopOnEscape)
    return () => {
      desktop.removeEventListener('change', stopOnSmallScreen)
      window.removeEventListener('keydown', stopOnEscape)
    }
  }, [])

  useEffect(() => {
    if (!connected || full) setActive(false)
  }, [connected, full])

  const pointFrom = (clientX: number, clientY: number, surface: HTMLElement): Point => {
    const rect = surface.getBoundingClientRect()
    return {
      x: Math.max(0, Math.min(1, (clientX - rect.left) / rect.width)),
      y: Math.max(0, Math.min(1, (clientY - rect.top) / rect.height)),
    }
  }

  const isProtected = (clientX: number, clientY: number) =>
    document.elementsFromPoint(clientX, clientY).some((element) =>
      element.closest('.seats, .tablecards, .phase'),
    )

  const collect = (event: ReactPointerEvent<HTMLDivElement>) => {
    const samples = event.nativeEvent.getCoalescedEvents?.() ?? [event.nativeEvent]
    for (const sample of samples.length ? samples : [event.nativeEvent]) {
      if (isProtected(sample.clientX, sample.clientY)) {
        flush()
        pendingRef.current = []
        continue
      }
      const point = pointFrom(sample.clientX, sample.clientY, event.currentTarget)
      const previous = pendingRef.current.at(-1)
      if (!previous) {
        pendingRef.current = [point]
      } else if (previous.x !== point.x || previous.y !== point.y) {
        drawPath({ color, width, points: [previous, point] })
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
    send({ action: 'draw', points, color, width })
    pendingRef.current = [pending.at(-1)!]
    lastSentAtRef.current = performance.now()
  }

  const finishStroke = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (active) {
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
          if (!active || event.button !== 0) return
          if (isProtected(event.clientX, event.clientY)) return
          pendingRef.current = [pointFrom(event.clientX, event.clientY, event.currentTarget)]
          lastSentAtRef.current = performance.now()
          event.currentTarget.setPointerCapture(event.pointerId)
        }}
        onPointerMove={(event) => {
          if (!active || pendingRef.current.length === 0 || !event.currentTarget.hasPointerCapture(event.pointerId)) return
          collect(event)
          if (performance.now() - lastSentAtRef.current >= SEND_INTERVAL) flush()
        }}
        onPointerUp={finishStroke}
        onPointerCancel={(event) => {
          pendingRef.current = []
          if (event.currentTarget.hasPointerCapture(event.pointerId)) {
            event.currentTarget.releasePointerCapture(event.pointerId)
          }
        }}
      />
      <div className={`drawing-tools${active ? ' is-active' : ''}`}>
        {active && (
          <div className="drawing-tools__brush" aria-label="Pincel">
            <div className="drawing-tools__colors" aria-label="Color del pincel">
              {COLORS.map((option, index) => (
                <button
                  key={option}
                  type="button"
                  className={`drawing-tools__color${color === index ? ' is-selected' : ''}`}
                  style={{ '--brush-color': option } as CSSProperties}
                  aria-label={`Color ${index + 1}`}
                  aria-pressed={color === index}
                  onClick={() => setColor(index)}
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
          </div>
        )}
        <button
          type="button"
          className={`drawing-tools__button${active ? ' is-active' : ''}`}
          aria-pressed={active}
          disabled={!connected || full}
          title={full ? 'La mesa está llena de dibujos' : 'Dibujar sobre la mesa'}
          onClick={() => setActive((value) => !value)}
        >
          {active ? 'Terminar' : 'Pintar'}
        </button>
        {room.you?.isHost && room.drawing.length > 0 && (
          <button type="button" className="drawing-tools__button" onClick={() => send({ action: 'clear_drawing' })}>
            Limpiar
          </button>
        )}
      </div>
    </>
  )
}
