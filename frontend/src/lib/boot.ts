// La animación de arranque es CSS puro (ver index.html) y la lanza /boot-start.js cuando
// cartas y tipografía están listas. Sus movimientos fuertes terminan hacia los 0,9 s; el
// resto es tiempo para verla asentada antes de quitarla.
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
    // Red de seguridad: si boot-start.js no llegó a ejecutarse, arranca aquí.
    if (!boot.dataset.start) {
      boot.dataset.start = String(performance.now())
      boot.classList.add('is-go')
    }
    // El tiempo mínimo se cuenta desde que la animación arrancó de verdad, no desde la carga.
    const wait = MIN_MS - (performance.now() - Number(boot.dataset.start))
    if (wait > 0) await new Promise<void>((r) => setTimeout(r, wait))
  }
 
  boot.classList.add('is-hiding')
  setTimeout(() => boot.remove(), 500)
}
 