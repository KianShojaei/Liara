import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// COPILOT_PORT lets scripts/dev_up.ps1 point the proxy at a fallback backend port.
const backendPort = process.env.COPILOT_PORT || '8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': { target: `http://127.0.0.1:${backendPort}`, changeOrigin: true } },
  },
})
