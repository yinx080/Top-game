import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { defineConfig, type Connect, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'

const PUBLIC_DIR = resolve(import.meta.dirname, 'public')

/**
 * Páginas estáticas con URL limpia (`/legal`, `/como-se-juega`) también en
 * desarrollo.
 *
 * En producción las sirve FastAPI desde `ruta/index.html` (ver `spa()` en
 * `backend/app/main.py`). Vite, en cambio, no sabe de URLs limpias y contesta
 * con el `index.html` del juego, así que salía la animación de entrada en vez
 * de la página. Este middleware imita al backend: `/ruta` sirve
 * `public/ruta/index.html` y `/ruta/` redirige a la versión sin barra.
 */
function staticPages(): Plugin {
  const middleware: Connect.NextHandleFunction = (req, res, next) => {
    const [path] = (req.url ?? '/').split(/[?#]/)
    const clean = decodeURIComponent(path).replace(/^\/+|\/+$/g, '')
    if (!clean || clean.includes('..') || !/^[\w-]+(\/[\w-]+)*$/.test(clean)) return next()

    const file = resolve(PUBLIC_DIR, clean, 'index.html')
    if (!file.startsWith(PUBLIC_DIR) || !existsSync(file)) return next()

    if (path.endsWith('/')) {
      res.statusCode = 301
      res.setHeader('Location', `/${clean}`)
      res.end()
      return
    }
    res.setHeader('Content-Type', 'text/html; charset=utf-8')
    res.end(readFileSync(file))
  }

  return {
    name: 'static-pages',
    configureServer: (server) => void server.middlewares.use(middleware),
    configurePreviewServer: (server) => void server.middlewares.use(middleware),
  }
}

// En desarrollo el frontend habla con FastAPI a través del proxy, así que el
// código de cliente usa siempre rutas relativas y funciona igual cuando es el
// propio backend quien sirve el build.
export default defineConfig({
  plugins: [react(), staticPages()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/ws': { target: 'ws://127.0.0.1:8000', ws: true },
    },
  },
  build: { outDir: 'dist', assetsDir: 'assets', sourcemap: false },
})
