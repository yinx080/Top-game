import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import { App } from './App'
import { dismissBoot } from './lib/boot'
import { sfx } from './lib/sfx'
import './styles/global.css'

// Los navegadores no dejan sonar nada hasta que hay un gesto del usuario:
// aprovechamos el primero que llegue para arrancar el contexto de audio.
const unlock = () => sfx.unlock()
window.addEventListener('pointerdown', unlock, { once: true })
window.addEventListener('keydown', unlock, { once: true })

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

void dismissBoot()