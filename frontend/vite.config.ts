/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The Python server serves the built app, so `vite build` writes into the package.
export default defineConfig({
  plugins: [react()],
  build: { outDir: process.env.VERCEL ? "dist" : "../src/realis/web/dist", emptyOutDir: true, sourcemap: !process.env.VERCEL },
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8000", "/cases": "http://127.0.0.1:8000" },
  },
  test: { environment: "jsdom", globals: false },
});
