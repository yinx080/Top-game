import { useSyncExternalStore } from 'react'

/**
 * Enrutado por hash, a mano.
 *
 * Sólo hay dos pantallas y el hash sobrevive a cualquier hosting estático sin
 * configurar nada, así que no merece la pena traer una librería entera.
 */
export type Route = { name: 'home' } | { name: 'room'; code: string }

export function parseHash(hash: string): Route {
  const clean = hash.replace(/^#\/?/, '').trim()
  const match = /^room\/([A-Za-z0-9]{1,12})$/.exec(clean)
  if (match) return { name: 'room', code: match[1].toUpperCase() }
  return { name: 'home' }
}

function subscribe(callback: () => void): () => void {
  window.addEventListener('hashchange', callback)
  return () => window.removeEventListener('hashchange', callback)
}

let cachedHash = ''
let cachedRoute: Route = { name: 'home' }

function getSnapshot(): Route {
  if (window.location.hash !== cachedHash) {
    cachedHash = window.location.hash
    cachedRoute = parseHash(cachedHash)
  }
  return cachedRoute
}

export function useRoute(): Route {
  return useSyncExternalStore(subscribe, getSnapshot, () => ({ name: 'home' }) as Route)
}

export function goHome(): void {
  window.location.hash = '/'
}

export function goToRoom(code: string): void {
  window.location.hash = `/room/${code.toUpperCase()}`
}

export function roomLink(code: string): string {
  return `${location.origin}${location.pathname}#/room/${code.toUpperCase()}`
}
