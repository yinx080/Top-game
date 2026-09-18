/**
 * Rótulo del juego.
 *
 * El efecto es el de un cartel de recreativa: tres copias desplazadas en rojo,
 * turquesa y oro. Se apoya en `data-text` para no repetir el texto en el DOM.
 */
export function Logo({ size = 'big' }: { size?: 'big' | 'small' }) {
  return (
    <div className={`logo logo--${size}`}>
      <span className="logo__word" data-text="TOP">
        TOP
      </span>
      <span className="logo__word logo__word--alt" data-text="CARD">
        CARD
      </span>
    </div>
  )
}
