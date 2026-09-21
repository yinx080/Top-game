// La animación de arranque es CSS puro (ver index.html). Sus movimientos fuertes terminan
// hacia los 0,9 s; el resto es tiempo para verla asentada antes de quitarla.
const MIN_MS = 1400

const appPainted = () =>
  document.fonts.ready.then(
    () => new Promise<void>((r) => requestAnimationFrame(() => requestAnimationFrame(() => r()))),
  )

export async function dismissBoot() {
  const boot = document.getElementById('boot')
  if (!boot) return
  await appPainted()

  // Con «reducir movimiento» el escenario está oculto: no hay nada que esperar.
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  if (!reduced) {
    // La animación arranca cuando el navegador pinta la página por primera vez.
    const firstPaint = performance.getEntriesByName('first-paint')[0]?.startTime ?? 0
    const wait = MIN_MS - (performance.now() - firstPaint)
    if (wait > 0) await new Promise<void>((r) => setTimeout(r, wait))
  }

  boot.classList.add('is-hiding')
  setTimeout(() => boot.remove(), 500)
}