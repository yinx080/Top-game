/** Hora del servidor + tiempo monotónico transcurrido desde que llegó el estado.
 * No depende de que el reloj del teléfono coincida con el del servidor. */
export function remainingSeconds(deadline: number, serverNow: number, receivedAt: number, now: number): number {
  return Math.max(0, Math.ceil(deadline - serverNow - Math.max(0, now - receivedAt) / 1000))
}
