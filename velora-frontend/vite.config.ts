import fs from "fs"
import path from "path"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

const proxyTarget = process.env.VITE_PROXY_TARGET || "http://localhost:8011"
const httpsKey = process.env.VITE_HTTPS_KEY
const httpsCert = process.env.VITE_HTTPS_CERT
const devHttps = httpsKey && httpsCert && fs.existsSync(httpsKey) && fs.existsSync(httpsCert)
  ? {
      key: fs.readFileSync(httpsKey),
      cert: fs.readFileSync(httpsCert),
    }
  : undefined

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    https: devHttps,
    proxy: {
      "/api": {
        target: proxyTarget,
        changeOrigin: true,
      },
    },
  },
  preview: {
    allowedHosts: true,
    https: devHttps,
    proxy: {
      "/api": {
        target: proxyTarget,
        changeOrigin: true,
      },
    },
  },
})
