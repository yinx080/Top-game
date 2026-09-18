/**
 * Sonidos de la partida sintetizados con WebAudio.
 *
 * Preferimos generarlos a cargar ficheros: pesan cero, no hay licencias que
 * arrastrar y el resultado (ondas cuadradas cortas) es exactamente el timbre
 * arcade que pide el diseño.
 */

export type SoundName =
  | 'click'
  | 'deal'
  | 'place'
  | 'flip'
  | 'turn'
  | 'vote'
  | 'join'
  | 'leave'
  | 'win'
  | 'lose'

let context: AudioContext | null = null
let master: GainNode | null = null
let volume = 0.6
let muted = false

function ensureContext(): AudioContext | null {
  if (typeof window === 'undefined') return null
  if (!context) {
    const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
    if (!Ctor) return null
    context = new Ctor()
    master = context.createGain()
    master.gain.value = muted ? 0 : volume
    master.connect(context.destination)
  }
  // Los navegadores arrancan el audio suspendido hasta que hay un gesto.
  if (context.state === 'suspended') void context.resume()
  return context
}

export const sfx = {
  /** Se llama en el primer clic del usuario para desbloquear el audio. */
  unlock(): void {
    ensureContext()
  },

  setVolume(next: number): void {
    volume = Math.max(0, Math.min(1, next))
    if (master) master.gain.value = muted ? 0 : volume
  },

  setMuted(next: boolean): void {
    muted = next
    if (master) master.gain.value = muted ? 0 : volume
  },

  play(name: SoundName): void {
    if (muted || volume === 0) return
    const ctx = ensureContext()
    if (!ctx || !master) return
    const at = ctx.currentTime
    switch (name) {
      case 'click':
        blip(ctx, master, at, 660, 0.05, 'square', 0.22)
        break
      case 'vote':
        blip(ctx, master, at, 520, 0.06, 'square', 0.25)
        blip(ctx, master, at + 0.06, 780, 0.07, 'square', 0.2)
        break
      case 'deal':
        for (let i = 0; i < 4; i += 1) swish(ctx, master, at + i * 0.09, 0.07, 0.16)
        break
      case 'place':
        swish(ctx, master, at, 0.09, 0.3)
        blip(ctx, master, at, 180, 0.09, 'triangle', 0.3)
        break
      case 'flip':
        swish(ctx, master, at, 0.06, 0.22)
        blip(ctx, master, at + 0.02, 900, 0.05, 'square', 0.16)
        break
      case 'turn':
        blip(ctx, master, at, 880, 0.1, 'triangle', 0.26)
        blip(ctx, master, at + 0.1, 1320, 0.14, 'triangle', 0.2)
        break
      case 'join':
        blip(ctx, master, at, 523, 0.08, 'square', 0.2)
        blip(ctx, master, at + 0.08, 784, 0.1, 'square', 0.18)
        break
      case 'leave':
        blip(ctx, master, at, 440, 0.09, 'square', 0.18)
        blip(ctx, master, at + 0.09, 294, 0.12, 'square', 0.16)
        break
      case 'win':
        [523, 659, 784, 1047].forEach((freq, i) =>
          blip(ctx, master!, at + i * 0.11, freq, 0.16, 'square', 0.24),
        )
        break
      case 'lose':
        [392, 330, 262].forEach((freq, i) =>
          blip(ctx, master!, at + i * 0.15, freq, 0.22, 'sawtooth', 0.2),
        )
        break
    }
  },
}

function blip(
  ctx: AudioContext,
  out: GainNode,
  at: number,
  frequency: number,
  duration: number,
  type: OscillatorType,
  peak: number,
): void {
  const osc = ctx.createOscillator()
  const gain = ctx.createGain()
  osc.type = type
  osc.frequency.setValueAtTime(frequency, at)
  gain.gain.setValueAtTime(0, at)
  gain.gain.linearRampToValueAtTime(peak, at + 0.008)
  gain.gain.exponentialRampToValueAtTime(0.0001, at + duration)
  osc.connect(gain).connect(out)
  osc.start(at)
  osc.stop(at + duration + 0.02)
}

/** Ruido filtrado: el roce de una carta contra el tapete. */
function swish(ctx: AudioContext, out: GainNode, at: number, duration: number, peak: number): void {
  const frames = Math.floor(ctx.sampleRate * duration)
  const buffer = ctx.createBuffer(1, frames, ctx.sampleRate)
  const data = buffer.getChannelData(0)
  for (let i = 0; i < frames; i += 1) data[i] = (Math.random() * 2 - 1) * (1 - i / frames)

  const source = ctx.createBufferSource()
  source.buffer = buffer
  const filter = ctx.createBiquadFilter()
  filter.type = 'bandpass'
  filter.frequency.setValueAtTime(1400, at)
  filter.frequency.exponentialRampToValueAtTime(420, at + duration)
  const gain = ctx.createGain()
  gain.gain.setValueAtTime(peak, at)
  gain.gain.exponentialRampToValueAtTime(0.0001, at + duration)
  source.connect(filter).connect(gain).connect(out)
  source.start(at)
}
