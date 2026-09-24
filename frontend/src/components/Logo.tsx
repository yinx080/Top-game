/**
 * Rótulo del juego.
 *
 * El efecto es el de un cartel de recreativa: tres copias desplazadas en rojo,
 * turquesa y oro. Se apoya en `data-text` para no repetir el texto en el DOM.
 *
 * En la portada va como `h1`: es el título de la página para los buscadores.
 * El `aria-label` da el nombre de la marca junto, igual que el dominio.
 */
export function Logo({ size = 'big', as: Tag = 'div' }: { size?: 'big' | 'small'; as?: 'div' | 'h1' }) {
  return (
    <Tag className={`logo logo--${size}`} aria-label={Tag === 'h1' ? 'TopCards' : undefined}>
      <span className="logo__word" data-text="TOP">
        TOP
      </span>
      <span className="logo__word logo__word--alt" data-text="CARDS">
        CARDS
      </span>
    </Tag>
  )
}
