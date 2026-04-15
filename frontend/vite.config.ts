import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
  },
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    host: '0.0.0.0',
    // Port may be overridden from the CLI (RUN.sh passes --port based on
    // FRONTEND_PORT in .env). 5173 stays as the fallback for `npm run dev`.
    port: Number(process.env.FRONTEND_PORT) || 5173,
    proxy: {
      '/api': {
        target: `http://localhost:${process.env.BACKEND_PORT || '8000'}`,
        changeOrigin: true,
      },
    },
  },
})
