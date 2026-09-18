import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// En desarrollo el frontend habla con FastAPI a través del proxy, así que el
// código de cliente usa siempre rutas relativas y funciona igual cuando es el
// propio backend quien sirve el build.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/ws': { target: 'ws://127.0.0.1:8000', ws: true },
    },
  },
  build: { outDir: 'dist', assetsDir: 'assets', sourcemap: false },
})
