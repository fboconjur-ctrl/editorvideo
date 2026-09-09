import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Build output goes straight into backend/static, so FastAPI can serve the
// whole app from a single process/port — no separate frontend server needed.
export default defineConfig({
  plugins: [react()],
  base: "/",
  build: {
    outDir: "../backend/static",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
