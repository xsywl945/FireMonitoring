import { readFileSync } from "node:fs"
import { dirname, resolve } from "node:path"
import { fileURLToPath } from "node:url"
import vue from "@vitejs/plugin-vue"
import { defineConfig } from "vite"

const root = dirname(fileURLToPath(import.meta.url))
const config = JSON.parse(readFileSync(resolve(root, "../../config.json"), "utf-8")) as {
  server: { host: string; port: number }
}

const api = `http://${config.server.host}:${config.server.port}`

export default defineConfig({
  plugins: [vue()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: { "/api": { target: api, changeOrigin: true } },
  },
  preview: {
    host: "127.0.0.1",
    port: 5173,
    proxy: { "/api": { target: api, changeOrigin: true } },
  },
})
