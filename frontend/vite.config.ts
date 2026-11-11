/// <reference types="vitest" />
import { fileURLToPath, URL } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  // Dev server only: forward /api to the Django API so the browser sees one origin
  // and the refresh-token cookie works without CORS.
  const apiTarget = env.VITE_DEV_API_PROXY_TARGET || "http://localhost:8000";

  return {
    plugins: [react()],
    resolve: {
      alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
    },
    server: {
      port: 5173,
      proxy: { "/api": { target: apiTarget, changeOrigin: true } },
    },
    test: {
      globals: true,
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
      css: false,
      restoreMocks: true,
      // Tests run against a fixed absolute API origin so MSW can match requests.
      env: { VITE_API_BASE_URL: "http://localhost:3000/api/v1" },
    },
  };
});
