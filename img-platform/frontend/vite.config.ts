import { defineConfig, loadEnv } from 'vite'
import vue from "@vitejs/plugin-vue"
import { resolve } from "path"
import { readFileSync, existsSync } from "fs"

const CANVAS_DIST = resolve(__dirname, "canvas-dist")

const MIME_TYPES: Record<string, string> = {
  html: "text/html",
  js: "application/javascript",
  mjs: "application/javascript",
  css: "text/css",
  json: "application/json",
  png: "image/png",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  gif: "image/gif",
  svg: "image/svg+xml",
  ico: "image/x-icon",
  webp: "image/webp",
  woff: "font/woff",
  woff2: "font/woff2",
  ttf: "font/ttf",
  eot: "application/vnd.ms-fontobject",
}

function canvasMiddleware(req: any, res: any, next: any) {
  let urlPath = req.url.split("?")[0]

  if (urlPath.startsWith("/canvas") === false) return next()
  urlPath = urlPath.replace(/^\/canvas\/?/, "/")
  if (urlPath === "/") urlPath = "/index.html"

  const filePath = resolve(CANVAS_DIST, "." + urlPath)

  if (filePath.startsWith(CANVAS_DIST) === false) {
    res.statusCode = 403
    res.end("Forbidden")
    return
  }

  if (existsSync(filePath) === false) {
    const indexPath = resolve(CANVAS_DIST, "index.html")
    if (existsSync(indexPath)) {
      const content = readFileSync(indexPath, "utf-8")
      res.setHeader("Content-Type", "text/html")
      res.setHeader("Cache-Control", "no-cache")
      res.end(content)
      return
    }
    res.statusCode = 404
    res.end("Canvas not found")
    return
  }

  const ext = filePath.split(".").pop() || ""
  res.setHeader("Content-Type", MIME_TYPES[ext] || "application/octet-stream")
  res.setHeader("Cache-Control", "public, max-age=3600")
  res.end(readFileSync(filePath))
}

export default defineConfig(() => {
  const env = loadEnv("", process.cwd(), "")
  const apiBaseUrl = env.VITE_API_BASE_URL || "http://localhost:8000"

  return {
    plugins: [vue()],
    resolve: {
      alias: {
        "@": resolve(__dirname, "src"),
      },
    },
    server: {
      host: "0.0.0.0",
      port: 5173,
      proxy: {
        "/api": {
          target: apiBaseUrl,
          changeOrigin: true,
        },
        "/minimax-output": {
          target: apiBaseUrl,
          changeOrigin: true,
          rewrite: (path) => path,
        },
        "/uploads": {
          target: apiBaseUrl,
          changeOrigin: true,
          rewrite: (path) => path,
        },
      },
      configureServer(server) {
        server.middlewares.use("/canvas", canvasMiddleware)
      },
    },
  }
})
