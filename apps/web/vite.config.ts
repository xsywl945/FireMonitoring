import { fileURLToPath, URL } from 'node:url'
import vue from '@vitejs/plugin-vue'
import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    plugins: [vue()],
    resolve: {
      alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
    },
    server: {
      host: '127.0.0.1',
      port: 5173,
      strictPort: true,
      proxy: {
        '/api': { target: env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8080', changeOrigin: true },
        '/ws': { target: env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8080', ws: true },
        '/inference': {
          target: env.VITE_INFERENCE_PROXY_TARGET || 'http://127.0.0.1:8091',
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/inference/, ''),
        },
      },
    },
    build: {
      target: 'es2022',
      outDir: 'dist',
      sourcemap: true,
      chunkSizeWarningLimit: 900,
      rollupOptions: {
        output: {
          manualChunks: {
            vue: ['vue', 'vue-router', 'pinia'],
            element: ['element-plus', '@element-plus/icons-vue'],
            charts: ['echarts'],
          },
        },
      },
    },
  }
})
