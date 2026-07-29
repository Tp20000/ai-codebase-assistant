import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  void env;

  return {
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
          configure: (proxy) => {
            proxy.on("proxyReq", (proxyReq) => {
              const url = proxyReq.path;
              const segments = url.split("?")[0].split("/").filter(Boolean);
              const last = segments[segments.length - 1] ?? "";
              const isId =
                /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(last) ||
                /^\d+$/.test(last);
              if (isId && url.endsWith("/")) {
                proxyReq.path = url.slice(0, -1);
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
      minify: "esbuild",
      chunkSizeWarningLimit: 3000,
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (id.includes("node_modules")) {
              if (id.includes("react-dom") || id.includes("react-router")) {
                return "vendor-react";
              }
              if (id.includes("framer-motion")) {
                return "vendor-motion";
              }
              if (id.includes("@tanstack") || id.includes("zustand")) {
                return "vendor-state";
              }
              if (id.includes("recharts") || id.includes("d3-")) {
                return "vendor-charts";
              }
              if (id.includes("@monaco-editor") || id.includes("monaco-editor")) {
                return "vendor-monaco";
              }
              if (id.includes("reactflow") || id.includes("@xyflow")) {
                return "vendor-flow";
              }
              return "vendor";
            }
          },
        },
      },
    },

    test: {
      globals: true,
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
    },
  };
});