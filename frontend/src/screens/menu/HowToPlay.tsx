import { Modal } from '../../components/ui'

const STEPS = [
  {
    icon: '🂡',
    title: 'Una carta cada uno',
    text: 'Se reparte una carta al azar por jugador. Nadie ve la de los demás: el As es la más baja y la K la más alta.',
  },
  {
    icon: '💡',
    title: 'Un tema para el top',
    text: 'Cada ronda se propone y se vota un tema anónimo, de hasta 180 caracteres. Si gana el tuyo, la sala se lo queda para futuras partidas.',
  },
  {
    icon: '🗣️',
    title: 'Coloca y di una palabra',
    text: 'Prepara tu palabra o frase mientras juegan los demás. Tienes 30 segundos por defecto para colocar: el anfitrión puede ajustar el tiempo incluso durante el turno. Si se agota, se salta tu turno.',
  },
  {
    icon: '🏆',
    title: 'Se destapa de menor a mayor',
    text: 'Al final se voltean una a una. Ganáis todos si quedan ordenadas; los empates no rompen el orden.',
  },
]

export function HowToPlay({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <Modal open={open} title="Cómo se juega" onClose={onClose} width={560}>
      <ol className="howto">
        {STEPS.map((step) => (
          <li key={step.title} className="howto__step">
            <span className="howto__icon" aria-hidden="true">
              {step.icon}
            </span>
            <div>
              <strong className="howto__title">{step.title}</strong>
              <p className="hint">{step.text}</p>
            </div>
          </li>
        ))}
      </ol>
      <p className="hint" style={{ marginTop: 16 }}>
        Es un juego cooperativo: o gana el grupo entero, o pierde el grupo entero.
      </p>
    </Modal>
  )
}
