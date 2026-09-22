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
  | 'chat'
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

/** Tic-tac de «se acaba el tiempo». Es un fichero real (no se sintetiza) y se decodifica una sola vez. */
const TICK_URL = '/art/tictac.mp3'
let tickBuffer: AudioBuffer | null = null
let tickLoading = false
let tickWanted = false
let tickSource: AudioBufferSourceNode | null = null
let tickGain: GainNode | null = null

function loadTick(ctx: AudioContext): void {
  if (tickBuffer || tickLoading) return
  tickLoading = true
  fetch(TICK_URL)
    .then((response) => {
      if (!response.ok) throw new Error(`tictac ${response.status}`)
      return response.arrayBuffer()
    })
    .then((data) => ctx.decodeAudioData(data))
    .then((buffer) => {
      tickBuffer = buffer
      // Si el aviso empezó mientras se descargaba, arranca ahora.
      if (tickWanted && !tickSource) playTick()
    })
    .catch(() => {
      tickLoading = false // se reintentará la próxima vez
    })
}

function playTick(): void {
  if (!context || !master || !tickBuffer || context.state !== 'running') return
  stopTick(false)
  const source = context.createBufferSource()
  const gain = context.createGain()
  source.buffer = tickBuffer
  source.connect(gain).connect(master)
  source.onended = () => {
    if (tickSource === source) {
      tickSource = null
      tickGain = null
    }
  }
  source.start()
  tickSource = source
  tickGain = gain
}

function stopTick(fade: boolean): void {
  if (!tickSource || !tickGain || !context) return
  const source = tickSource
  const gain = tickGain
  tickSource = null
  tickGain = null
  const now = context.currentTime
  try {
    if (fade) {
      gain.gain.setValueAtTime(gain.gain.value, now)
      gain.gain.linearRampToValueAtTime(0, now + 0.12)
      source.stop(now + 0.14)
    } else {
      source.stop()
    }
  } catch {
    /* ya estaba parado */
  }
}

/**
 * Fanfarria de victoria. También es un fichero real; el arpegio sintetizado
 * se queda como red de seguridad por si todavía no ha cargado.
 *
 * El fichero viene normalizado a ~-2 dBFS de pico (igual que el tic-tac), así
 * que se atenúa un poco aquí para que no tape al resto de efectos. Si suena
 * fuerte o flojo de más, este número es el que hay que tocar.
 */
const WIN_URL = '/art/win.mp3'
const WIN_GAIN = 0.9
let winBuffer: AudioBuffer | null = null
let winLoading = false

function loadWin(ctx: AudioContext): void {
  if (winBuffer || winLoading) return
  winLoading = true
  fetch(WIN_URL)
    .then((response) => {
      if (!response.ok) throw new Error(`win ${response.status}`)
      return response.arrayBuffer()
    })
    .then((data) => ctx.decodeAudioData(data))
    .then((buffer) => {
      winBuffer = buffer
    })
    .catch(() => {
      winLoading = false // se reintentará la próxima vez
    })
}

/** Suena el fichero de victoria. Devuelve false si todavía no está listo. */
function playWinSample(): boolean {
  if (!context || !master || !winBuffer || context.state !== 'running') return false
  const source = context.createBufferSource()
  const gain = context.createGain()
  source.buffer = winBuffer
  gain.gain.value = WIN_GAIN
  source.connect(gain).connect(master)
  source.start()
  return true
}

export const sfx = {
  /** Se llama en el primer clic del usuario para desbloquear el audio. */
  unlock(): void {
    const ctx = ensureContext()
    if (ctx) {
      loadTick(ctx)
      loadWin(ctx)
    }
  },

  /** Empieza el tic-tac (una sola vez, desde el principio). Respeta volumen y silencio. */
  startTicking(): void {
    tickWanted = true
    const ctx = ensureContext()
    if (!ctx) return
    if (tickBuffer) playTick()
    else loadTick(ctx)
  },

  /** Corta el tic-tac con un fundido corto para que no haya chasquido. */
  stopTicking(): void {
    tickWanted = false
    stopTick(true)
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
      case 'chat':
        blip(ctx, master, at, 1046, 0.04, 'triangle', 0.16)
        blip(ctx, master, at + 0.05, 1568, 0.06, 'triangle', 0.12)
        break
      case 'leave':
        blip(ctx, master, at, 440, 0.09, 'square', 0.18)
        blip(ctx, master, at + 0.09, 294, 0.12, 'square', 0.16)
        break
      case 'win':
        // Manda el fichero; si no ha cargado, suena el arpegio de siempre.
        if (!playWinSample()) {
          [523, 659, 784, 1047].forEach((freq, i) =>
            blip(ctx, master!, at + i * 0.11, freq, 0.16, 'square', 0.24),
          )
        }
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