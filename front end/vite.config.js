import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  // Tailwind v4 si integra come plugin di Vite: niente tailwind.config.js né PostCSS.
  plugins: [react(), tailwindcss()],
})
