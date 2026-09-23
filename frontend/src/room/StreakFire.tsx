import { useEffect, useRef } from 'react'

interface Particle {
  x: number
  y: number
  vx: number
  vy: number
  size: number
  age: number
  life: number
}

export function StreakFire({
  streak,
  reducedMotion,
  variant,
}: {
  streak: number
  reducedMotion: boolean
  variant: 'indicator' | 'table'
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const context = canvas.getContext('2d')
    if (!context) return

    let width = 0
    let height = 0
    let frame = 0
    let lastFrame = performance.now()
    let spawnCarry = 0
    const particles: Particle[] = []
    const level = Math.min(Math.max(streak, 0), 10)
    const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const still = reducedMotion || prefersReduced

    const resize = () => {
      const rect = canvas.getBoundingClientRect()
      width = rect.width
      height = rect.height
      const dpr = Math.min(window.devicePixelRatio || 1, variant === 'table' ? 1.5 : 2)
      canvas.width = Math.max(1, Math.round(width * dpr))
      canvas.height = Math.max(1, Math.round(height * dpr))
      context.setTransform(dpr, 0, 0, dpr, 0, 0)
    }

    const drawGlow = () => {
      context.clearRect(0, 0, width, height)
      if (!level) return
      const glow = context.createLinearGradient(0, height, 0, Math.max(0, height - 90 - level * 4))
      glow.addColorStop(0, `rgb(255 91 20 / ${0.2 + level * 0.025})`)
      glow.addColorStop(0.55, `rgb(255 174 45 / ${0.1 + level * 0.012})`)
      glow.addColorStop(1, 'transparent')
      context.fillStyle = glow
      context.fillRect(0, variant === 'table' ? height - 110 - level * 4 : 0, width, height)
    }

    const spawn = () => {
      const table = variant === 'table'
      let x = table ? Math.random() * width : width * (0.22 + Math.random() * 0.56)
      let y = height + 4
      let vx = (Math.random() - 0.5) * (table ? 18 : 10)
      let vy = -(25 + Math.random() * (table ? 35 + level * 3 : 20 + level * 2))

      if (table && level >= 4 && Math.random() < Math.min(0.15 + level * 0.035, 0.48)) {
        const left = Math.random() < 0.5
        x = left ? 2 : width - 2
        y = height * (0.25 + Math.random() * 0.7)
        vx = (left ? 1 : -1) * (8 + Math.random() * 15)
        vy *= 0.55
      }
      particles.push({
        x,
        y,
        vx,
        vy,
        size: (table ? 5 : 3) + Math.random() * (table ? 8 + level * 0.4 : 5),
        age: 0,
        life: 0.55 + Math.random() * (table ? 0.75 : 0.45),
      })
    }

    const draw = (now: number) => {
      frame = window.requestAnimationFrame(draw)
      const minFrame = variant === 'table' ? 32 : 16
      if (now - lastFrame < minFrame) return
      const dt = Math.min((now - lastFrame) / 1000, 0.05)
      lastFrame = now
      context.clearRect(0, 0, width, height)

      const rate = variant === 'table' ? 7 + level * 7 : 12 + level * 3
      spawnCarry += rate * dt
      while (spawnCarry >= 1) {
        spawn()
        spawnCarry -= 1
      }

      context.globalCompositeOperation = 'lighter'
      for (let index = particles.length - 1; index >= 0; index -= 1) {
        const particle = particles[index]
        particle.age += dt
        if (particle.age >= particle.life) {
          particles.splice(index, 1)
          continue
        }
        particle.x += particle.vx * dt
        particle.y += particle.vy * dt
        particle.vx += (Math.random() - 0.5) * 12 * dt
        const remaining = 1 - particle.age / particle.life
        const radius = particle.size * (0.35 + remaining * 0.65)
        context.fillStyle = remaining > 0.62
          ? `rgb(255 225 105 / ${remaining * 0.85})`
          : remaining > 0.3
            ? `rgb(255 126 28 / ${remaining * 0.8})`
            : `rgb(224 55 25 / ${remaining * 0.65})`
        context.beginPath()
        context.ellipse(particle.x, particle.y, radius * 0.7, radius, 0, 0, Math.PI * 2)
        context.fill()
      }
      context.globalCompositeOperation = 'source-over'
    }

    const observer = new ResizeObserver(() => {
      resize()
      if (still) drawGlow()
    })
    observer.observe(canvas)
    resize()
    if (still) drawGlow()
    else if (level) frame = window.requestAnimationFrame(draw)
    else context.clearRect(0, 0, width, height)

    return () => {
      window.cancelAnimationFrame(frame)
      observer.disconnect()
    }
  }, [reducedMotion, streak, variant])

  return <canvas ref={canvasRef} className={`streak-fire streak-fire--${variant}`} aria-hidden="true" />
}
