import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [
    react({ jsxRuntime: "automatic" }),
  ],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    host: "0.0.0.0",
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        secure: false,
        configure: (proxy, _options) => {
          proxy.on("proxyReq", (proxyReq, req, _res) => {
            // Vite proxy sometimes adds trailing slash — strip it
            // FastAPI has redirect_slashes=False so /projects/id/ = 404
            const original = proxyReq.path;
            // Only strip if last segment looks like an ID (UUID or number)
            // Keep trailing slash for collection endpoints like /projects/
            const segments = original.split("?")[0].split("/").filter(Boolean);
            const last = segments[segments.length - 1] ?? "";
            const isId =
              /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(last) ||
              /^\d+$/.test(last);
            if (isId && original.includes("?")) {
              proxyReq.path = original.replace(/\/\?/, "?");
            } else if (isId && original.endsWith("/")) {
              proxyReq.path = original.slice(0, -1);
            }
            if (proxyReq.path !== original) {
              console.log(`[proxy] ${original} -> ${proxyReq.path}`);
            }
          });
        },
      },
      "/ws": {
        target: "ws://localhost:8000",
        changeOrigin: true,
        ws: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
  },
});