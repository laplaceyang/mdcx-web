import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:9801', changeOrigin: true },
      '/ws': { target: 'ws://127.0.0.1:9801', ws: true },
    },
  },
  build: {
    chunkSizeWarningLimit: 2500,
  },
})
