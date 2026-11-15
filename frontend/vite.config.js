import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// Backend the dev server proxies /api to. Override to use another port: MARS_API_URL=http://localhost:8001 npm run dev
const apiUrl = process.env.MARS_API_URL ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': apiUrl,
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.js'],
    // Leaflet cannot draw vector layers in jsdom; every test gets a lightweight react-leaflet double.
    alias: {
      'react-leaflet': fileURLToPath(new URL('./src/test/reactLeafletMock.jsx', import.meta.url)),
    },
  },
})
